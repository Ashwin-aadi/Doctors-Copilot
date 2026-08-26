from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.ml.lab_flags import _classify_trend, _flag_value, flag_labs
from app.ml.schemas_ml import LabFlagInput


def test_flag_value_high_and_critical() -> None:
    assert _flag_value(1.0, 0.6, 1.3) == "normal"
    assert _flag_value(1.5, 0.6, 1.3) == "high"
    assert _flag_value(3.1, 0.6, 1.3) == "critical"


def test_flag_value_low_and_unknown() -> None:
    assert _flag_value(0.5, 0.6, 1.3) == "low"
    assert _flag_value(0.2, 0.6, 1.3) == "critical"  # below ref_low / CRITICAL_RANGE_MULTIPLIER
    assert _flag_value(1.0, None, None) == "unknown"
    assert _flag_value("text", 0.6, 1.3) == "unknown"


def test_classify_trend_rising_falling_stable() -> None:
    assert _classify_trend(1.2, [1.0]) == "rising"
    assert _classify_trend(0.8, [1.0]) == "falling"
    assert _classify_trend(1.02, [1.0]) == "stable"
    assert _classify_trend(1.0, []) is None


@pytest.mark.asyncio
async def test_flag_labs_creatinine_critical(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)

    scalars_result = MagicMock()
    scalars_result.all.return_value = []
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_result
    db.execute = AsyncMock(return_value=execute_result)

    results = [
        LabFlagInput(
            test_name="Creatinine",
            normalized_name="creatinine",
            value=3.1,
            unit="mg/dL",
            confidence=0.9,
        )
    ]
    out = await flag_labs(db, uuid4(), results)
    assert len(out) == 1
    assert out[0].flag in ("critical", "high")


@pytest.mark.asyncio
async def test_flag_labs_trend_rising(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.get = AsyncMock(return_value=None)

    scalars_result = MagicMock()
    scalars_result.all.return_value = [1.0]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_result
    db.execute = AsyncMock(return_value=execute_result)

    results = [
        LabFlagInput(
            test_name="Creatinine",
            normalized_name="creatinine",
            value=1.2,
            unit="mg/dL",
            ref_low=0.6,
            ref_high=1.3,
            confidence=0.9,
        )
    ]
    out = await flag_labs(db, uuid4(), results)
    assert out[0].trend == "rising"
