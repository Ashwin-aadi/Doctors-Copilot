from pathlib import Path

import pytest

from app.ml.ocr import _cluster_rows, run_ocr

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "ml" / "fixtures"
FIXTURE_NAMES = ["cbc", "lft", "kft", "lipid", "thyroid"]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_text_layer_fixtures_skip_ocr_and_extract_cleanly(name: str) -> None:
    result = run_ocr(FIXTURES_DIR / f"{name}.pdf")
    assert result["engine"] == "pdf_text"
    assert result["mean_confidence"] > 0.6
    assert len(result["pages"]) >= 1
    page = result["pages"][0]
    assert page["text"]
    assert all(0 <= b["conf"] <= 1 for b in page["blocks"])
    assert all(len(b["bbox"]) == 4 for b in page["blocks"])


def test_cbc_text_layer_recovers_lab_values() -> None:
    result = run_ocr(FIXTURES_DIR / "cbc.pdf")
    text = result["pages"][0]["text"]
    assert "Haemoglobin" in text
    assert "Platelet Count" in text


def test_noisy_scan_runs_real_ocr_engine() -> None:
    result = run_ocr(FIXTURES_DIR / "cbc_noisy_scan.pdf")
    assert len(result["pages"]) >= 1
    assert result["engine"] in {"paddle_en", "paddle_devanagari", "tesseract", "unavailable"}
    assert 0.0 <= result["mean_confidence"] <= 1.0
    for page in result["pages"]:
        for b in page["blocks"]:
            assert 0.0 <= b["conf"] <= 1.0
            assert len(b["bbox"]) == 4


def test_result_shape_matches_schema() -> None:
    result = run_ocr(FIXTURES_DIR / "cbc.pdf")
    assert set(result.keys()) == {"pages", "engine", "mean_confidence"}
    page = result["pages"][0]
    assert set(page.keys()) == {"page", "text", "blocks", "tables"}
    assert page["page"] == 0
    if page["blocks"]:
        block = page["blocks"][0]
        assert set(block.keys()) == {"bbox", "text", "conf"}


def test_cluster_rows_groups_by_y_and_splits_columns_by_x_gap() -> None:
    blocks = [
        {"bbox": [0, 0, 40, 20], "text": "Haemoglobin", "conf": 1.0},
        {"bbox": [200, 2, 230, 20], "text": "10.2", "conf": 1.0},
        {"bbox": [400, 1, 420, 20], "text": "g/dL", "conf": 1.0},
        {"bbox": [0, 30, 40, 50], "text": "Platelet", "conf": 1.0},
        {"bbox": [200, 31, 230, 50], "text": "1.42", "conf": 1.0},
    ]
    rows = _cluster_rows(blocks)
    assert len(rows) == 2
    assert rows[0] == ["Haemoglobin", "10.2", "g/dL"]
    assert rows[1] == ["Platelet", "1.42"]


def test_cluster_rows_empty_input() -> None:
    assert _cluster_rows([]) == []
