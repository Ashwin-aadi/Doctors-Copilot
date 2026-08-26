"""OCR service: turn preprocessed pages into text + per-block confidence + tables.

`run_ocr(path)` reuses V1.2's `to_pages` output. A page that already carries a
real embedded text layer (`engine="pdf_text"`) is read straight from the PDF's
text/word geometry -- OCR is never run on it, since it would only add error to
text that is already exact. Everything else runs PaddleOCR (English first,
falling back to Devanagari for Hindi-script clinic headers when confidence is
low), then Tesseract if PaddleOCR is unavailable or still low-confidence;
whichever run scored highest is kept.
"""

from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any, TypedDict

import cv2
import fitz
import numpy as np
import structlog

from app.ml.preprocess import Page, to_pages

logger = structlog.get_logger(__name__)

CONFIDENCE_RERUN_THRESHOLD = 0.60
ROW_TOLERANCE = 0.6
COLUMN_GAP_MULTIPLIER = 2.0
PDF_TEXT_DPI = 300


class Block(TypedDict):
    bbox: list[float]
    text: str
    conf: float


class OcrPage(TypedDict):
    page: int
    text: str
    blocks: list[Block]
    tables: list[list[list[str]]]


class OcrResult(TypedDict):
    pages: list[OcrPage]
    engine: str
    mean_confidence: float


_paddle_cache: dict[str, Any] = {}


def run_ocr(path: str | Path) -> OcrResult:
    path = Path(path)
    pages = to_pages(path)

    ocr_pages: list[OcrPage] = []
    engines_used: list[str] = []
    all_confs: list[float] = []
    pdf_doc = fitz.open(str(path)) if path.suffix.lower() == ".pdf" else None

    try:
        for idx, page in enumerate(pages):
            if page.engine == "pdf_text" and pdf_doc is not None and idx < len(pdf_doc):
                blocks = _pdf_text_blocks(pdf_doc[idx])
                engine = "pdf_text"
            else:
                blocks, engine = _ocr_page(page)

            text = "\n".join(b["text"] for b in blocks)
            tables = _extract_tables(blocks)
            ocr_pages.append({"page": idx, "text": text, "blocks": blocks, "tables": tables})
            engines_used.append(engine)
            all_confs.extend(b["conf"] for b in blocks)
    finally:
        if pdf_doc is not None:
            pdf_doc.close()

    mean_confidence = round(sum(all_confs) / len(all_confs), 4) if all_confs else 0.0
    return {
        "pages": ocr_pages,
        "engine": _dominant_engine(engines_used),
        "mean_confidence": mean_confidence,
    }


def _dominant_engine(engines_used: list[str]) -> str:
    if not engines_used:
        return "unavailable"
    counts: dict[str, int] = {}
    for e in engines_used:
        counts[e] = counts.get(e, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _pdf_text_blocks(pdf_page: fitz.Page) -> list[Block]:
    """Exact text extraction for a page with a real text layer -- no OCR."""
    scale = PDF_TEXT_DPI / 72.0
    lines: dict[tuple[int, int], list[tuple[float, float, float, float, str]]] = {}
    for x0, y0, x1, y1, word, block_no, line_no, _word_no in pdf_page.get_text("words"):
        stripped = word.strip()
        if not stripped:
            continue
        lines.setdefault((block_no, line_no), []).append((x0, y0, x1, y1, stripped))

    blocks: list[Block] = []
    for key in sorted(lines):
        words = lines[key]
        x0 = min(w[0] for w in words)
        y0 = min(w[1] for w in words)
        x1 = max(w[2] for w in words)
        y1 = max(w[3] for w in words)
        text = " ".join(w[4] for w in words)
        blocks.append(
            {
                "bbox": [x0 * scale, y0 * scale, x1 * scale, y1 * scale],
                "text": text,
                "conf": 1.0,
            }
        )
    return blocks


def _ocr_page(page: Page) -> tuple[list[Block], str]:
    candidates: list[tuple[str, list[Block]]] = []

    en_blocks = _try_paddle(page, lang="en")
    if en_blocks is not None:
        candidates.append(("paddle_en", en_blocks))

    if not candidates or _mean_conf(candidates[0][1]) < CONFIDENCE_RERUN_THRESHOLD:
        dev_blocks = _try_paddle(page, lang="devanagari")
        if dev_blocks is not None:
            candidates.append(("paddle_devanagari", dev_blocks))

        tess_blocks = _try_tesseract(page)
        if tess_blocks is not None:
            candidates.append(("tesseract", tess_blocks))

    if not candidates:
        return [], "unavailable"

    engine, blocks = max(candidates, key=lambda c: _mean_conf(c[1]))
    return blocks, engine


def _mean_conf(blocks: list[Block]) -> float:
    if not blocks:
        return 0.0
    return sum(b["conf"] for b in blocks) / len(blocks)


def _get_paddle(lang: str) -> Any:
    if lang not in _paddle_cache:
        from paddleocr import PaddleOCR

        _paddle_cache[lang] = PaddleOCR(
            use_angle_cls=True, lang=lang, det_db_box_thresh=0.5, show_log=False
        )
    return _paddle_cache[lang]


def _try_paddle(page: Page, lang: str) -> list[Block] | None:
    try:
        ocr = _get_paddle(lang)
        arr = np.asarray(page)
        img = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR) if arr.ndim == 2 else arr
        result = ocr.ocr(img, cls=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ml.ocr.paddle_failed", lang=lang, error=str(exc))
        return None

    if not result or result[0] is None:
        return []

    blocks: list[Block] = []
    for box, (text, score) in result[0]:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        blocks.append(
            {"bbox": [min(xs), min(ys), max(xs), max(ys)], "text": text, "conf": float(score)}
        )
    return blocks


def _try_tesseract(page: Page) -> list[Block] | None:
    try:
        import pytesseract
        from pytesseract import Output

        pytesseract.get_tesseract_version()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ml.ocr.tesseract_unavailable", error=str(exc))
        return None

    try:
        arr = np.asarray(page)
        data = pytesseract.image_to_data(
            arr, config="--psm 6 --oem 3 -l eng+hin", output_type=Output.DICT
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ml.ocr.tesseract_failed", error=str(exc))
        return None

    blocks: list[Block] = []
    for i, text in enumerate(data["text"]):
        if not text.strip():
            continue
        conf_raw = float(data["conf"][i])
        if conf_raw < 0:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        blocks.append({"bbox": [x, y, x + w, y + h], "text": text.strip(), "conf": conf_raw / 100.0})
    return blocks


def _extract_tables(blocks: list[Block]) -> list[list[list[str]]]:
    """Row/column clustering only -- see DECISIONS.md for why PP-Structure,
    though importable, is not invoked here."""
    rows = _cluster_rows(blocks)
    return [rows] if rows else []


def _cluster_rows(blocks: list[Block]) -> list[list[str]]:
    if not blocks:
        return []

    heights = [b["bbox"][3] - b["bbox"][1] for b in blocks if b["bbox"][3] > b["bbox"][1]]
    median_height = median(heights) if heights else 1.0
    row_tolerance = ROW_TOLERANCE * median_height

    def y_centroid(b: Block) -> float:
        return (b["bbox"][1] + b["bbox"][3]) / 2

    ordered = sorted(blocks, key=y_centroid)
    rows: list[list[Block]] = []
    for b in ordered:
        yc = y_centroid(b)
        if rows and abs(yc - y_centroid(rows[-1][-1])) <= row_tolerance:
            rows[-1].append(b)
        else:
            rows.append([b])

    char_widths = [
        (b["bbox"][2] - b["bbox"][0]) / max(len(b["text"]), 1) for b in blocks if b["text"]
    ]
    median_char_width = median(char_widths) if char_widths else 1.0
    column_gap = COLUMN_GAP_MULTIPLIER * median_char_width

    table_rows: list[list[str]] = []
    for row in rows:
        row = sorted(row, key=lambda b: b["bbox"][0])
        cells: list[str] = []
        current_words: list[str] = [row[0]["text"]]
        prev_x1 = row[0]["bbox"][2]
        for b in row[1:]:
            gap = b["bbox"][0] - prev_x1
            if gap > column_gap:
                cells.append(" ".join(current_words))
                current_words = [b["text"]]
            else:
                current_words.append(b["text"])
            prev_x1 = b["bbox"][2]
        cells.append(" ".join(current_words))
        table_rows.append(cells)

    return table_rows
