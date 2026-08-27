"""Tool adapters for the RAG/orchestration layer.

`build_summary` and `suggest_medications` implement the frozen §4.2
signatures verbatim -- no other consumer exists yet, so there is nothing to
reconcile.

`extract_entities`, `check_interactions`, and `flag_labs` instead match the
call convention `app/rag/tool_bridge.py` already ships with on `main`:
`check_interactions(patient_id, medications: list)` and
`flag_labs(patient_id, labs: list[dict])`, both returning plain
dict/list-of-dict shapes rather than the `InteractionRequest`/`LabResultOut`
objects in the original §4.2 pseudocode. See "DRIFT: tool_bridge call
signature" in docs/DECISIONS.md -- that bridge is real, already-merged
integration code (`app/services/visit.py._safety` and
`app/rag/clinical_rag.py.build_brief` call it this way today), so matching
it is what actually wires the tools up; matching the pseudocode instead
would leave `tool_bridge`'s own `except Exception` swallow every call and
silently keep returning its typed-empty fallback forever.

Every function: internal 20s timeout, typed empty result on any failure
(never raises), and a `TOOL_SCHEMAS` map for LLM tool-calling.
`check_interactions`/`flag_labs` are additionally cached on a stable hash of
their request (the DB-backed ones can't safely cache across patients'
mutable state for long, so caching is in-process and unbounded per process
lifetime -- fine for the request-scoped, short-lived nature of these calls).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any
from uuid import UUID

from app.ml.lab_flags import flag_labs as _flag_labs_impl
from app.ml.med_suggest import suggest_medications as _suggest_medications_impl
from app.ml.ner import extract as _extract_entities_impl
from app.ml.safety import check_interactions as _check_interactions_impl
from app.ml.schemas_ml import (
    EntityBundle,
    InteractionRequest,
    LabFlagInput,
    MedSuggestRequest,
    SummaryRequest,
)
from app.ml.summary import build_summary as _build_summary_impl
from app.schemas.ml import MedCandidate, SoapSummary

_TIMEOUT_SECONDS = 20.0
_cache: dict[str, Any] = {}


def _cache_key(name: str, payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return f"{name}:{hashlib.sha256(raw.encode()).hexdigest()}"


async def extract_entities(text: str) -> EntityBundle:
    try:
        return await asyncio.wait_for(_extract_entities_impl(text), timeout=_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 -- typed empty result, never raise to the caller
        return EntityBundle()


async def check_interactions(patient_id: UUID | str, medications: list) -> dict:
    """`(patient_id, medications: list[dict | str]) -> dict` -- matches
    `app/rag/tool_bridge.py`'s call and return convention exactly."""
    key = _cache_key("check_interactions", {"patient_id": str(patient_id), "medications": medications})
    if key in _cache:
        return _cache[key]

    empty = {"pairs": [], "allergy_conflicts": [], "contraindications": []}
    try:
        med_names = [
            (med.get("name") if isinstance(med, dict) else med) for med in medications
        ]
        med_names = [m for m in med_names if m]
        if not med_names:
            return empty
        req = InteractionRequest(medications=med_names)
        report = await asyncio.wait_for(_check_interactions_impl(req), timeout=_TIMEOUT_SECONDS)
        result = report.model_dump(mode="json")
    except Exception:  # noqa: BLE001
        result = empty

    _cache[key] = result
    return result


async def flag_labs(patient_id: UUID | str, labs: list[dict]) -> list[dict]:
    """`(patient_id, labs: list[dict]) -> list[dict]` -- matches
    `app/rag/tool_bridge.py`'s call and return convention exactly."""
    key = _cache_key("flag_labs", {"patient_id": str(patient_id), "labs": labs})
    if key in _cache:
        return _cache[key]

    try:
        items = [
            LabFlagInput(
                test_name=lab.get("test_name", ""),
                normalized_name=lab.get("normalized_name") or lab.get("test_name", ""),
                value=lab.get("value"),
                unit=lab.get("unit"),
                ref_low=lab.get("ref_low"),
                ref_high=lab.get("ref_high"),
                confidence=lab.get("confidence", 1.0),
            )
            for lab in labs
            if lab.get("value") is not None
        ]
        if not items:
            return []

        from app.db.session import SessionLocal

        async with SessionLocal() as db:
            out = await asyncio.wait_for(
                _flag_labs_impl(db, UUID(str(patient_id)), items), timeout=_TIMEOUT_SECONDS
            )
        result = [row.model_dump(mode="json") for row in out]
    except Exception:  # noqa: BLE001
        result = []

    _cache[key] = result
    return result


async def suggest_medications(req: MedSuggestRequest) -> list[MedCandidate]:
    try:
        return await asyncio.wait_for(_suggest_medications_impl(req), timeout=_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001
        return []


async def build_summary(req: SummaryRequest) -> SoapSummary:
    try:
        return await asyncio.wait_for(_build_summary_impl(req), timeout=_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001
        return SoapSummary(
            subjective="", objective="", assessment="", plan="", citations=[], confidence=0.0
        )


TOOL_SCHEMAS: dict[str, dict] = {
    "extract_entities": {
        "name": "extract_entities",
        "description": "Extract drug/condition/allergen entities from clinical text.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    "check_interactions": {
        "name": "check_interactions",
        "description": "Check drug-drug interactions, allergy conflicts, and contraindications.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "medications": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["patient_id", "medications"],
        },
    },
    "flag_labs": {
        "name": "flag_labs",
        "description": "Flag abnormal lab results against reference ranges and prior trend.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "labs": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["patient_id", "labs"],
        },
    },
    "suggest_medications": {
        "name": "suggest_medications",
        "description": "Rank candidate medications for a set of conditions, filtered for safety.",
        "parameters": {
            "type": "object",
            "properties": {
                "conditions": {"type": "array", "items": {"type": "string"}},
                "current_medications": {"type": "array", "items": {"type": "string"}},
                "allergies": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["conditions"],
        },
    },
    "build_summary": {
        "name": "build_summary",
        "description": "Build a SOAP clinical summary for a visit.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "string"},
                "visit_id": {"type": "string"},
            },
            "required": ["patient_id", "visit_id"],
        },
    },
}
