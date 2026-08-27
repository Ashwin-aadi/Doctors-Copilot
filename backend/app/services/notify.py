"""Notification delivery (checkpoint P3.2): writes a `Notification` row,
publishes `notify.{user_id}` to Redis for Abhishek's WS layer, and makes a
best-effort attempt at the user's actual channels -- email (aiosmtplib to a
dev MailHog instance, falling back to `infra/mail/*.eml` when unreachable)
and SMS (against a TRAI DLT-registered template contract; with no gateway
configured it writes `infra/sms/*.txt` instead, carrying the same DLT entity
id / template id / 6-char sender header a real gateway call would need, so
wiring one in later is a config change, not a rewrite).

`preferred_language` has no column on `app/db/models/user.py::User` (off
limits -- see docs/DECISIONS.md), so it's read through a local Core `Table`,
same pattern as `app/services/consent.py` uses for `consents`.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Column, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.redis_client import redis_client
from app.db.models.audit import Notification
from app.db.models.patient import Patient
from app.db.models.scheduling import Doctor
from app.db.models.user import User
from app.db.session import SessionLocal

IST = ZoneInfo("Asia/Kolkata")

NOTIFICATION_TYPES: tuple[str, ...] = (
    "appointment_confirmed",
    "appointment_rescheduled",
    "lab_order_approved",
    "results_ready",
    "emergency_escalated",
    "prescription_ready",
)

# Placeholder TRAI DLT template ids -- swap for the real registered ids once
# the gateway/entity is registered; per-type so that's a config-only change.
DLT_TEMPLATE_IDS: dict[str, str] = {
    t: f"170710000000000{i:04d}" for i, t in enumerate(NOTIFICATION_TYPES, start=1)
}

_TEMPLATE_ROOT = Path(__file__).parent / "templates"

_metadata = MetaData()
_users_table = Table(
    "users",
    _metadata,
    Column("id", PGUUID(as_uuid=True), primary_key=True),
    Column("email", String(255)),
    Column("phone", String(32)),
    Column("preferred_language", String(8)),
)


def format_ist(dt: datetime | None) -> str:
    """`DD-MM-YYYY hh:mm AM/PM` in IST -- never a bare UTC timestamp."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(IST).strftime("%d-%m-%Y %I:%M %p")


def _load_template(locale: str, type_: str) -> str:
    path = _TEMPLATE_ROOT / locale / f"{type_}.txt"
    if not path.exists():
        path = _TEMPLATE_ROOT / "en" / f"{type_}.txt"
    return path.read_text(encoding="utf-8").strip()


def render_notification(type_: str, payload: dict[str, Any], locale: str = "en") -> str:
    template = _load_template(locale, type_)
    safe_payload = {**payload}
    if "slot_time_ist" in safe_payload and isinstance(safe_payload["slot_time_ist"], datetime):
        safe_payload["slot_time_ist"] = format_ist(safe_payload["slot_time_ist"])
    try:
        return template.format(**safe_payload)
    except KeyError:
        # A payload missing a placeholder the template expects degrades to
        # the raw template rather than raising -- delivery should never fail
        # because of a cosmetic formatting gap.
        return template


async def _lookup_user_channels(db: AsyncSession, user_id: UUID) -> tuple[str | None, str | None, str]:
    result = await db.execute(select(_users_table).where(_users_table.c.id == user_id))
    row = result.first()
    if row is None:
        return None, None, "en"
    locale = row.preferred_language or "en"
    return row.email, row.phone, locale if locale in ("en", "hi") else "en"


def _write_eml_fallback(to_addr: str, subject: str, body: str) -> None:
    settings = get_settings()
    out_dir = Path(settings.mail_fallback_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    (out_dir / f"{uuid.uuid4().hex}.eml").write_bytes(bytes(msg))


async def send_email(to_addr: str, subject: str, body: str) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        import aiosmtplib

        await aiosmtplib.send(
            msg, hostname=settings.smtp_host, port=settings.smtp_port, timeout=5
        )
    except Exception:
        # No MailHog running (or aiosmtplib not importable in this sandbox,
        # see docs/DECISIONS.md's standing infra-gap note) -- write the
        # message to disk instead of losing it silently.
        _write_eml_fallback(to_addr, subject, body)


def send_sms(phone: str, template_id: str, template_vars: dict[str, Any]) -> None:
    """Fire-and-forget against a TRAI DLT-registered template contract. No
    real gateway is configured in this hackathon build, so the rendered
    payload (entity id, template id, 6-char sender header, variables) is
    written to `infra/sms/*.txt` -- structurally identical to what a real
    gateway call would send, so wiring one in later only changes this
    function's body, not any caller."""
    settings = get_settings()
    out_dir = Path(settings.sms_fallback_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "to": phone,
        "dlt_entity_id": settings.dlt_entity_id,
        "dlt_template_id": template_id,
        "sender_header": settings.dlt_sender_header,
        "vars": template_vars,
        "sent_at": format_ist(datetime.now(UTC)),
    }
    (out_dir / f"{uuid.uuid4().hex}.txt").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )


async def _resolve_display_name(db: AsyncSession, user: User | None) -> str | None:
    if user is None:
        return None
    if user.role == "patient":
        result = await db.execute(select(Patient.name).where(Patient.user_id == user.id))
        return result.scalar_one_or_none()
    if user.role == "doctor":
        result = await db.execute(select(Doctor.name).where(Doctor.user_id == user.id))
        return result.scalar_one_or_none()
    return None


async def notify(
    user_id: UUID, type_: str, payload: dict[str, Any], db: AsyncSession | None = None
) -> Notification:
    async def _run(session: AsyncSession) -> Notification:
        record = Notification(
            user_id=user_id, type=type_, payload=payload, created_at=datetime.now(UTC)
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)

        await redis_client.publish(
            f"notify.{user_id}",
            json.dumps(
                {"id": str(record.id), "type": type_, "payload": payload}, default=str
            ),
        )

        email, phone, locale = await _lookup_user_channels(session, user_id)
        body = render_notification(type_, payload, locale)

        if email:
            await send_email(email, f"Doctor's Copilot: {type_.replace('_', ' ')}", body)
        if phone:
            send_sms(phone, DLT_TEMPLATE_IDS.get(type_, "unknown"), payload)

        return record

    if db is not None:
        return await _run(db)
    async with SessionLocal() as session:
        return await _run(session)
