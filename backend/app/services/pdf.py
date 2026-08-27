"""PDF export (checkpoint P3.3). WeasyPrint renders A4 HTML templates to
PDF bytes; all timestamps go through `notify.format_ist` (IST,
DD-MM-YYYY hh:mm AM/PM) and every amount is formatted `en-IN` with a `RUPEE
SIGN` prefix, per the India-context locale rules.

Prescription/lab-order templates satisfy the Telemedicine Practice
Guidelines, 2020: clinic name/address, patient name/age/sex/ABHA, IST
date-time, the drug/test list, and a footer carrying the doctor's name,
qualification, specialty and NMC/SMC registration number. A locked record is
stamped DOCTOR-APPROVED plus a footer with `content_hash`/`approved_by`/
`approved_at`; an unlocked one is stamped DRAFT -- NOT FOR CLINICAL USE in
English and Hindi.

`doctors.registration_council`/`registration_year` and `clinics.
facility_type` have no ORM columns (see docs/DECISIONS.md); read here
through the same local Core `Table` pattern `app/services/notify.py` and
`app/services/consent.py` already use.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from babel.numbers import format_currency
from sqlalchemy import Column, Integer, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.db.models.clinical import LabOrder, Prescription, Visit
from app.db.models.patient import Patient
from app.db.models.scheduling import Clinic, Doctor
from app.db.models.user import User
from app.db.session import SessionLocal
from app.services.notify import format_ist

_TEMPLATE_ROOT = Path(__file__).parent / "templates"

_metadata = MetaData()
_doctors_table = Table(
    "doctors",
    _metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("registration_council", String(64)),
    Column("registration_year", Integer),
)
_clinics_table = Table(
    "clinics",
    _metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("facility_type", String(32)),
)

Kind = Literal["summary", "prescription", "lab_order"]


def _load_template(kind: Kind, locale: str) -> str:
    filename = f"{kind}.html" if locale == "en" else f"{kind}.{locale}.html"
    path = _TEMPLATE_ROOT / filename
    if not path.exists():
        path = _TEMPLATE_ROOT / f"{kind}.html"
    return path.read_text(encoding="utf-8")


def _render(template: str, mapping: dict[str, str]) -> str:
    html = template
    for key, value in mapping.items():
        html = html.replace("{{" + key + "}}", value)
    return html


def _age_from_dob(dob: date | None) -> str:
    if dob is None:
        return "N/A"
    today = date.today()
    years = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return str(years)


def format_inr(amount: float) -> str:
    return format_currency(amount, "INR", locale="en_IN")


async def _generic_alternative(drug_name: str) -> str | None:
    """Jan Aushadhi generic lookup via Niyati's real brand->generic service
    (`app/services/mapping/india_drugs.py::to_generic`), which shipped after
    this checkpoint's original TEMP-ADAPTER (a local `medications` table
    query) was first written -- switched over to the real service instead of
    keeping the workaround now that it's available. Returns `None` (empty
    generic column) on any miss/lookup failure rather than blocking export."""
    from app.services.mapping.india_drugs import to_generic

    try:
        mapping = await to_generic(name=drug_name, rxcui=None)
    except Exception:
        return None
    if not mapping.generics:
        return None
    return mapping.generics[0].name


async def _doctor_extra_fields(db: AsyncSession, doctor_id: UUID) -> dict:
    result = await db.execute(_doctors_table.select().where(_doctors_table.c.id == doctor_id))
    row = result.first()
    if row is None:
        return {"registration_council": None, "registration_year": None}
    return {
        "registration_council": row.registration_council,
        "registration_year": row.registration_year,
    }


def _status_banner(locked: bool, locale: str) -> tuple[str, str]:
    """Returns (banner_html, watermark_html). Both stamps are always
    bilingual (English + Hindi), per spec -- independent of the template's
    own `locale`, since the watermark must be unambiguous to any reader."""
    if locked:
        text = "DOCTOR-APPROVED / डॉक्टर-अनुमोदित"
        banner = f'<div class="banner approved">{text}</div>'
        watermark = f'<div class="watermark">{text}</div>'
        return banner, watermark
    text = "DRAFT — NOT FOR CLINICAL USE / प्रारूप — नैदानिक उपयोग के लिए नहीं"
    banner = f'<div class="banner draft">{text}</div>'
    watermark = '<div class="watermark">DRAFT</div>'
    return banner, watermark


def _approval_footer(*, locked: bool, content_hash: str | None, approved_by_name: str | None, approved_at) -> str:
    if not locked:
        return ""
    return (
        '<div class="approval">'
        f"Approved by: {approved_by_name or 'N/A'} &middot; "
        f"Approved at: {format_ist(approved_at)} &middot; "
        f"Content hash: {content_hash or 'N/A'}"
        "</div>"
    )


async def _resolve_patient_doctor_clinic(
    db: AsyncSession, patient_id: UUID, doctor_id: UUID | None
) -> tuple[Patient, Doctor | None, Clinic | None]:
    patient = await db.get(Patient, patient_id)
    if patient is None:
        raise ApiError("NOT_FOUND", "patient not found", status_code=404)

    doctor: Doctor | None = None
    clinic: Clinic | None = None
    if doctor_id is not None:
        doctor = await db.get(Doctor, doctor_id)
        if doctor is not None:
            clinic = await db.get(Clinic, doctor.clinic_id)
    return patient, doctor, clinic


def _clinic_address(clinic: Clinic | None) -> str:
    if clinic is None:
        return "N/A"
    parts = [p for p in (clinic.state, clinic.pin_code) if p]
    return ", ".join(parts) if parts else "N/A"


async def _render_prescription_or_lab_order(
    db: AsyncSession, kind: Kind, entity_id: UUID, locale: str
) -> str:
    model = Prescription if kind == "prescription" else LabOrder
    record = await db.get(model, entity_id)
    if record is None:
        raise ApiError("NOT_FOUND", f"{kind.replace('_', ' ')} not found", status_code=404)

    visit = await db.get(Visit, record.visit_id)
    doctor_id = visit.doctor_id if visit is not None else None
    patient, doctor, clinic = await _resolve_patient_doctor_clinic(db, record.patient_id, doctor_id)

    approved_by_name = None
    if record.approved_by is not None:
        approver = await db.get(User, record.approved_by)
        if approver is not None and doctor is not None:
            approved_by_name = doctor.name

    doctor_extra = (
        await _doctor_extra_fields(db, doctor.id) if doctor is not None else {"registration_council": None}
    )

    if kind == "prescription":
        rows: list[str] = []
        for item in record.items or []:
            drug = item.get("drug") or item.get("name") or "N/A"
            dose = item.get("dose", "")
            frequency = item.get("frequency", "")
            duration = item.get("duration", "")
            generic = await _generic_alternative(drug)
            drug_cell = (
                f'<span class="generic">{generic}</span><span class="brand">{drug}</span>'
                if generic
                else f'<span class="generic">{drug}</span>'
            )
            rows.append(f"<tr><td>{drug_cell}</td><td>{dose}</td><td>{frequency}</td><td>{duration}</td></tr>")
        item_rows = "\n".join(rows) or "<tr><td colspan='4'>No items</td></tr>"
    else:
        rows = []
        for item in record.items or []:
            test = item.get("test") or item.get("name") or "N/A"
            notes = item.get("notes", "")
            rows.append(f"<tr><td>{test}</td><td>{notes}</td></tr>")
        item_rows = "\n".join(rows) or "<tr><td colspan='2'>No items</td></tr>"

    banner, watermark = _status_banner(record.locked, locale)
    approval_footer = _approval_footer(
        locked=record.locked,
        content_hash=record.content_hash,
        approved_by_name=approved_by_name,
        approved_at=record.approved_at,
    )

    mapping = {
        "WATERMARK": watermark,
        "STATUS_BANNER": banner,
        "CLINIC_NAME": clinic.name if clinic else "N/A",
        "CLINIC_ADDRESS": _clinic_address(clinic),
        "PATIENT_NAME": patient.name,
        "PATIENT_AGE": _age_from_dob(patient.dob),
        "PATIENT_SEX": patient.sex or "N/A",
        "PATIENT_ABHA": patient.abha_id or "N/A",
        "DATE_IST": format_ist(record.created_at),
        "CONSULT_MODE": "Teleconsultation" if locale == "en" else "टेलीकंसल्टेशन",
        "DOCTOR_NAME": doctor.name if doctor else "N/A",
        "DOCTOR_QUALIFICATIONS": doctor.qualifications if doctor and doctor.qualifications else "N/A",
        "DOCTOR_SPECIALTY": ", ".join(doctor.specialties) if doctor and doctor.specialties else "General Medicine",
        "DOCTOR_REG_NO": doctor.nmc_reg_no if doctor and doctor.nmc_reg_no else "N/A",
        "DOCTOR_REG_COUNCIL": doctor_extra.get("registration_council") or "NMC",
        "CONSULT_FEE": format_inr(doctor.fee) if doctor else format_inr(0),
        "ITEM_ROWS": item_rows,
        "APPROVAL_FOOTER": approval_footer,
    }

    template = _load_template(kind, locale)
    return _render(template, mapping)


async def _render_summary(db: AsyncSession, patient_id: UUID, locale: str) -> str:
    patient = await db.get(Patient, patient_id)
    if patient is None:
        raise ApiError("NOT_FOUND", "patient not found", status_code=404)

    visit_result = await db.execute(
        select(Visit).where(Visit.patient_id == patient_id).order_by(Visit.created_at.desc()).limit(1)
    )
    visit = visit_result.scalars().first()

    def _list_html(items: list) -> str:
        if not items:
            return "<li>None recorded</li>"
        return "\n".join(f"<li>{item}</li>" for item in items)

    mapping = {
        "PATIENT_NAME": patient.name,
        "PATIENT_AGE": _age_from_dob(patient.dob),
        "PATIENT_SEX": patient.sex or "N/A",
        "PATIENT_ABHA": patient.abha_id or "N/A",
        "DATE_IST": format_ist(datetime.now(UTC)),
        "CONDITIONS": _list_html(patient.conditions or []),
        "ALLERGIES": _list_html(patient.allergies or []),
        "MEDICATIONS": _list_html(patient.medications or []),
        "VISIT_STATE": visit.state if visit else "No visits recorded",
        "VISIT_DATE": format_ist(visit.created_at) if visit else "N/A",
    }
    template = _load_template("summary", locale)
    return _render(template, mapping)


async def render(
    kind: Kind, entity_id: UUID, *, locale: str = "en", db: AsyncSession | None = None
) -> bytes:
    from weasyprint import HTML

    async def _run(session: AsyncSession) -> str:
        if kind == "summary":
            return await _render_summary(session, entity_id, locale)
        return await _render_prescription_or_lab_order(session, kind, entity_id, locale)

    if db is not None:
        html = await _run(db)
    else:
        async with SessionLocal() as session:
            html = await _run(session)

    return HTML(string=html).write_pdf()
