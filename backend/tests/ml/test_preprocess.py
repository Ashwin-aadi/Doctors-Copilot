from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.ml.preprocess import Page, _is_blank, quality_score, to_pages

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "ml" / "fixtures"
FIXTURE_NAMES = ["cbc", "lft", "kft", "lipid", "thyroid"]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_text_layer_fixtures_skip_ocr(name: str) -> None:
    pages = to_pages(FIXTURES_DIR / f"{name}.pdf")
    assert len(pages) >= 1
    assert pages[0].shape[0] > 1000
    assert pages[0].engine == "pdf_text"
    assert pages[0].text and len(pages[0].text.strip()) > 200


def test_noisy_scan_has_no_text_layer_and_runs_image_pipeline() -> None:
    pages = to_pages(FIXTURES_DIR / "cbc_noisy_scan.pdf")
    assert len(pages) >= 1
    assert pages[0].engine == "ocr"
    assert pages[0].shape[0] > 1000
    assert 0.0 <= pages[0].quality <= 1.0


def test_unsupported_extension_raises(tmp_path: Path) -> None:
    bogus = tmp_path / "report.docx"
    bogus.write_text("not a real document")
    with pytest.raises(ValueError):
        to_pages(bogus)


def test_blank_page_is_dropped(tmp_path: Path) -> None:
    blank_pdf = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(blank_pdf), pagesize=A4)
    c.showPage()
    c.save()
    pages = to_pages(blank_pdf)
    assert pages == []


def test_hard_cap_30_pages(tmp_path: Path) -> None:
    many_pages_pdf = tmp_path / "many.pdf"
    c = canvas.Canvas(str(many_pages_pdf), pagesize=A4)
    for i in range(35):
        c.drawString(50, 700, f"Report page {i} - Haemoglobin 12.5 g/dL result value line")
        c.drawString(50, 650, "Total Leukocyte Count 8200 cells/cu mm reference 4000-11000")
        c.showPage()
    c.save()
    pages = to_pages(many_pages_pdf)
    assert len(pages) <= 30


def test_quality_score_range_and_type() -> None:
    img = np.full((400, 400), 255, dtype=np.uint8)
    img[100:120, 50:350] = 0
    score = quality_score(img)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_is_blank_detects_ink_ratio() -> None:
    blank = np.full((200, 200), 255, dtype=np.uint8)
    assert _is_blank(blank)

    inked = np.full((200, 200), 255, dtype=np.uint8)
    inked[50:150, 50:150] = 0
    assert not _is_blank(inked)


def test_deskew_straightens_rotated_text_image(tmp_path: Path) -> None:
    img = Image.new("L", (900, 600), color=255)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    for y in range(80, 520, 40):
        draw.text((60, y), "Investigation Result Unit Reference Range", fill=0, font=font)
    rotated = img.rotate(6, expand=True, fillcolor=255)

    rotated_path = tmp_path / "skewed.png"
    rotated.save(rotated_path)

    pages = to_pages(rotated_path)
    assert len(pages) == 1
    assert pages[0].engine == "ocr"
    assert isinstance(pages[0], Page)


def test_page_is_ndarray_subclass_with_metadata() -> None:
    pages = to_pages(FIXTURES_DIR / "cbc.pdf")
    page = pages[0]
    assert isinstance(page, np.ndarray)
    assert hasattr(page, "engine")
    assert hasattr(page, "quality")
    assert hasattr(page, "low_quality")
