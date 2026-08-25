from pathlib import Path

import pytest
import yaml

from app.ml.lab_parser import parse_labs
from app.ml.ocr import run_ocr

ML_DIR = Path(__file__).resolve().parents[3] / "ml"
FIXTURES_DIR = ML_DIR / "fixtures"
EXPECTED_DIR = FIXTURES_DIR / "expected"
FIXTURE_NAMES = ["cbc", "lft", "kft", "lipid", "thyroid"]
FIELDS = ("normalized_name", "value", "unit", "flag")


def _load_expected(name: str) -> list[dict]:
    with (EXPECTED_DIR / f"{name}.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_field_accuracy_at_least_85_percent(name: str) -> None:
    result = run_ocr(FIXTURES_DIR / f"{name}.pdf")
    labs = parse_labs(result)
    by_name = {l.normalized_name: l for l in labs}
    expected = _load_expected(name)

    total = 0
    correct = 0
    for row in expected:
        got = by_name.get(row["normalized_name"])
        for field in FIELDS:
            total += 1
            if got is not None and getattr(got, field) == row[field]:
                correct += 1

    accuracy = correct / total
    assert accuracy >= 0.85, f"{name}: field accuracy {accuracy:.2%} ({correct}/{total})"


def test_cbc_recovers_core_names_and_confidence_bounds() -> None:
    labs = parse_labs(run_ocr(FIXTURES_DIR / "cbc.pdf"))
    names = {l.normalized_name for l in labs}
    assert {"hemoglobin", "wbc_count", "platelet_count"} <= names
    assert all(0 <= l.confidence <= 1 for l in labs)


def test_dedupes_across_table_and_line_modes() -> None:
    labs = parse_labs(run_ocr(FIXTURES_DIR / "cbc.pdf"))
    names = [l.normalized_name for l in labs]
    assert len(names) == len(set(names))


def test_low_flag_does_not_misfire_as_critical() -> None:
    labs = parse_labs(run_ocr(FIXTURES_DIR / "cbc.pdf"))
    hb = next(l for l in labs if l.normalized_name == "hemoglobin")
    assert hb.flag == "low"
    assert hb.value == 10.2


def test_emits_lab_result_out_shape() -> None:
    labs = parse_labs(run_ocr(FIXTURES_DIR / "cbc.pdf"))
    assert labs
    dumped = labs[0].model_dump()
    assert set(dumped.keys()) == {
        "test_name",
        "normalized_name",
        "value",
        "unit",
        "ref_low",
        "ref_high",
        "flag",
        "confidence",
        "page",
        "bbox",
    }
