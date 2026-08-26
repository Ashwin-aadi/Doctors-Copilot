"""Lab abnormality flagging and trend detection.

`flag_labs` fills in missing reference ranges from
`ml/data/reference_ranges.yaml` (sex-aware, via the patient's `Patient.sex`
row), sets `flag`, then attaches a `trend` by comparing each result against
the patient's prior `LabResult` rows for the same `normalized_name`
(>=10% relative change over >=2 points classifies rising/falling, else
stable). `trend` lives on `LabResultExtended`, an additive subclass of
Ashwin's `LabResultOut` -- his class is never touched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.clinical import LabResult
from app.db.models.patient import Patient
from app.ml.schemas_ml import LabFlagInput, LabResultExtended

DATA_DIR = Path(__file__).resolve().parents[3] / "ml" / "data"
TREND_THRESHOLD = 0.10

_REF_RANGES: dict | None = None


def _load_reference_ranges() -> dict:
    global _REF_RANGES
    if _REF_RANGES is None:
        path = DATA_DIR / "reference_ranges.yaml"
        with path.open(encoding="utf-8") as f:
            _REF_RANGES = yaml.safe_load(f) or {}
    return _REF_RANGES


def _resolve_range(normalized_name: str, sex: str | None) -> tuple[float | None, float | None]:
    entry = _load_reference_ranges().get(normalized_name)
    if entry is None:
        return None, None
    bucket = entry.get(sex) if sex in ("male", "female") else None
    bucket = bucket or entry.get("default", {})
    return bucket.get("low"), bucket.get("high")


def _flag_value(
    value: float | str, ref_low: float | None, ref_high: float | None
) -> Literal["critical", "high", "low", "normal", "unknown"]:
    if not isinstance(value, int | float):
        return "unknown"
    if ref_low is None and ref_high is None:
        return "unknown"

    critical_low = ref_low / 1.5 if ref_low is not None else None
    critical_high = ref_high * 1.5 if ref_high is not None else None

    if critical_high is not None and value >= critical_high:
        return "critical"
    if critical_low is not None and value > 0 and value <= critical_low:
        return "critical"
    if ref_high is not None and value > ref_high:
        return "high"
    if ref_low is not None and value < ref_low:
        return "low"
    return "normal"


def _classify_trend(current: float, history: list[float]) -> Literal["rising", "falling", "stable"] | None:
    points = [*history, current]
    if len(points) < 2:
        return None
    first, last = points[0], points[-1]
    if first == 0:
        return "stable"
    relative_change = (last - first) / abs(first)
    if relative_change >= TREND_THRESHOLD:
        return "rising"
    if relative_change <= -TREND_THRESHOLD:
        return "falling"
    return "stable"


async def flag_labs(
    db: AsyncSession, patient_id: UUID, results: list[LabFlagInput]
) -> list[LabResultExtended]:
    patient = await db.get(Patient, patient_id)
    sex = patient.sex if patient is not None else None

    out: list[LabResultExtended] = []
    for item in results:
        ref_low, ref_high = item.ref_low, item.ref_high
        if ref_low is None and ref_high is None:
            ref_low, ref_high = _resolve_range(item.normalized_name, sex)

        flag = _flag_value(item.value, ref_low, ref_high)

        trend = None
        if isinstance(item.value, int | float):
            prior_rows = (
                (
                    await db.execute(
                        select(LabResult.value_num)
                        .where(
                            LabResult.patient_id == patient_id,
                            LabResult.normalized_name == item.normalized_name,
                            LabResult.value_num.is_not(None),
                        )
                        .order_by(LabResult.observed_at.asc())
                    )
                )
                .scalars()
                .all()
            )
            history = [v for v in prior_rows if v is not None]
            trend = _classify_trend(float(item.value), history)

        out.append(
            LabResultExtended(
                test_name=item.test_name,
                normalized_name=item.normalized_name,
                value=item.value,
                unit=item.unit,
                ref_low=ref_low,
                ref_high=ref_high,
                flag=flag,
                confidence=item.confidence,
                page=item.page,
                trend=trend,
            )
        )
    return out
