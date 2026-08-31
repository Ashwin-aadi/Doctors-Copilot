"""Draft lab-order recommendation. Never auto-approves: the created `LabOrder`
row is always `status="draft"`, `locked=False` -- under Indian D&C Rules only
a registered practitioner may actually order a test, and approval is
Pratyaksh's captcha-gated endpoint (`app/api/v1/approvals.py`), not this one.
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.deps import CurrentUser, get_current_user, require_role
from app.core.errors import ApiError
from app.db.models.clinical import LabOrder, Visit
from app.db.models.patient import Patient
from app.db.session import SessionLocal
from app.services.rules.lab_rules import (
    catalogue,
    extract_symptom_keywords,
    merge_with_rag,
    recommend_labs,
)

router = APIRouter(prefix="/lab-orders", tags=["lab-orders"])

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


class RecommendIn(BaseModel):
    visit_id: UUID


def _season_for(now: dt.datetime) -> str:
    """June-September monsoon, March-May summer, else winter -- the coarse
    3-season split `packs/lab_panels.yaml` and the simulation both key off.
    """
    month = now.astimezone(IST).month
    if month in (6, 7, 8, 9):
        return "monsoon"
    if month in (3, 4, 5):
        return "summer"
    return "winter"


def _is_pregnant(conditions: list[str]) -> bool:
    return any("pregnan" in str(c).lower() for c in conditions)


async def _lab_order_context(visit_id: UUID, *, now: dt.datetime) -> tuple[dict, LabOrder | None]:
    """Gathers the deterministic, rule-engine inputs for a visit: symptoms
    (extracted from whatever free-text triage output exists), conditions
    (the patient's own record), specialty/severity (from the visit's triage
    result when one exists -- never silently defaulted to a routine tier if
    a real triage already ran), season (derived from `now`, never a wall-clock
    read) and region (the patient's state).
    """
    async with SessionLocal() as session:
        visit = await session.get(Visit, visit_id)
        if visit is None:
            raise ApiError("NOT_FOUND", "visit not found", status_code=404)
        patient = await session.get(Patient, visit.patient_id)
        conditions = list(patient.conditions or []) if patient is not None else []
        region = patient.state if patient is not None else None

    specialty = "general_medicine"
    severity_esi = 4
    free_text_parts: list[str] = []
    rag_labs = []

    if visit.triage_session_id is not None:
        try:
            from app.rag import triage_rag

            async with SessionLocal() as session:
                triage_result = await triage_rag.get_result(session, visit.triage_session_id)
            specialty = triage_result.specialty or specialty
            severity_esi = triage_result.severity_esi
            free_text_parts.extend(triage_result.red_flags)
            free_text_parts.append(triage_result.rationale)
            rag_labs = list(triage_result.suggested_labs)
        except ApiError:
            # no triage result finalized yet for this session -- fall back
            # to the visit's own defaults rather than failing the order.
            pass

    symptoms = extract_symptom_keywords(*free_text_parts, *conditions)

    ctx = {
        "symptoms": symptoms,
        "conditions": conditions,
        "specialty": specialty,
        "severity_esi": severity_esi,
        "season": _season_for(now),
        "region": region,
        "pregnant": _is_pregnant(conditions),
        "rag_labs": rag_labs,
        "patient_id": visit.patient_id,
    }
    return ctx, visit


@router.post("/recommend")
async def recommend_lab_order(
    body: RecommendIn, user: CurrentUser = Depends(require_role("doctor", "staff"))
) -> dict:
    now = dt.datetime.now(dt.UTC)
    ctx, visit = await _lab_order_context(body.visit_id, now=now)

    rule_labs = recommend_labs(
        symptoms=ctx["symptoms"],
        conditions=ctx["conditions"],
        specialty=ctx["specialty"],
        severity_esi=ctx["severity_esi"],
        season=ctx["season"],
        region=ctx["region"],
        pregnant=ctx["pregnant"],
    )
    merged = merge_with_rag(rule_labs, ctx["rag_labs"])

    async with SessionLocal() as session:
        order = LabOrder(
            id=uuid4(),
            visit_id=body.visit_id,
            patient_id=ctx["patient_id"],
            items=[item.model_dump(mode="json") for item in merged],
            status="draft",
            approved_by=None,
            approved_at=None,
            content_hash=None,
            locked=False,
        )
        session.add(order)
        # Point the visit at its current draft so the doctor's visit screen can
        # link straight through to the approval page. A visit only ever has one
        # order open at a time; a re-recommend supersedes the previous draft.
        visit_row = await session.get(Visit, body.visit_id)
        if visit_row is not None:
            visit_row.lab_order_id = order.id
        await session.commit()
        order_id = order.id

    return {
        "id": order_id,
        "visit_id": body.visit_id,
        "status": "draft",
        "locked": False,
        "items": [item.model_dump(mode="json") for item in merged],
    }


@router.get("/catalog")
async def lab_catalog(_user: CurrentUser = Depends(get_current_user)) -> list[dict]:
    """The tests a doctor may add to an order, straight from the rule pack --
    so the picker can never offer something the recommender itself does not
    recognise.
    """
    return [dict(item) for item in catalogue()]


@router.get("/{lab_order_id}")
async def get_lab_order(
    lab_order_id: UUID, user: CurrentUser = Depends(get_current_user)
) -> dict:
    async with SessionLocal() as session:
        order = await session.get(LabOrder, lab_order_id)
        if order is None:
            raise ApiError("NOT_FOUND", "lab order not found", status_code=404)
        return {
            "id": order.id,
            "visit_id": order.visit_id,
            "patient_id": order.patient_id,
            "status": order.status,
            "locked": order.locked,
            "items": order.items,
            "approved_by": order.approved_by,
            "approved_at": order.approved_at,
            # Set when this order amends one the doctor had already signed, so
            # the panel can say so rather than presenting it as the first.
            "supersedes_id": order.supersedes_id,
        }
