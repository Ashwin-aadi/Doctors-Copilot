"""Document ingestion & preprocessing: turn a raw file into clean page images.

`to_pages(path)` accepts PDFs and common image formats and returns one
processed page per kept page. A PDF page with a real embedded text layer
skips OCR entirely (faster and exact); everything else goes through the
image-cleanup pipeline (deskew -> denoise -> contrast -> threshold) so the
OCR tier in V1.3 gets the best possible input.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import fitz
import numpy as np

SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tiff"}

MAX_PAGES = 30
TEXT_LAYER_MIN_CHARS = 200
LOW_QUALITY_THRESHOLD = 0.25
BLANK_INK_RATIO = 0.005
DESKEW_MAX_ANGLE = 15.0
PDF_RENDER_DPI = 300


class Page(np.ndarray):
    """An ndarray of pixel data plus preprocessing metadata.

    Behaves exactly like the underlying array (`.shape`, indexing, etc. all
    work as normal) so downstream OCR code can treat `list[Page]` as
    `list[np.ndarray]`, while still carrying engine/quality info.
    """

    def __new__(
        cls,
        array: np.ndarray,
        *,
        engine: str = "ocr",
        quality: float = 1.0,
        low_quality: bool = False,
        text: str | None = None,
    ) -> Page:
        obj = np.asarray(array).view(cls)
        obj.engine = engine
        obj.quality = quality
        obj.low_quality = low_quality
        obj.text = text
        return obj

    def __array_finalize__(self, obj: Any) -> None:
        if obj is None:
            return
        self.engine = getattr(obj, "engine", "ocr")
        self.quality = getattr(obj, "quality", 1.0)
        self.low_quality = getattr(obj, "low_quality", False)
        self.text = getattr(obj, "text", None)


def to_pages(path: str | Path) -> list[Page]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported file type: {suffix!r} (path={path})")

    if suffix == ".pdf":
        pages = _pdf_to_pages(path)
    else:
        img = cv2.imread(str(path))
        if img is None:
            raise ValueError(f"could not read image: {path}")
        pages = [_process_image(img)]

    pages = pages[:MAX_PAGES]
    return [p for p in pages if not _is_blank(p)]


def _pdf_to_pages(path: Path) -> list[Page]:
    doc = fitz.open(str(path))
    try:
        pages: list[Page] = []
        for page_index in range(min(len(doc), MAX_PAGES)):
            pdf_page = doc[page_index]
            text = pdf_page.get_text()
            pix = pdf_page.get_pixmap(dpi=PDF_RENDER_DPI)
            arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n == 4:
                arr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
            elif pix.n == 3:
                arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

            if len(text.strip()) > TEXT_LAYER_MIN_CHARS:
                q = quality_score(arr)
                pages.append(
                    Page(arr, engine="pdf_text", quality=q, low_quality=q < LOW_QUALITY_THRESHOLD, text=text)
                )
            else:
                pages.append(_process_image(arr))
        return pages
    finally:
        doc.close()


def _process_image(img: np.ndarray) -> Page:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    deskewed = _deskew(gray)
    denoised = cv2.fastNlMeansDenoising(deskewed, h=10)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrasted = clahe.apply(denoised)
    thresh = cv2.adaptiveThreshold(
        contrasted, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    q = quality_score(thresh)
    return Page(thresh, engine="ocr", quality=q, low_quality=q < LOW_QUALITY_THRESHOLD)


def _deskew(gray: np.ndarray) -> np.ndarray:
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=150, minLineLength=gray.shape[1] // 4, maxLineGap=20
    )
    angle = 0.0
    if lines is not None:
        angles = []
        for x1, y1, x2, y2 in lines[:, 0]:
            a = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if -DESKEW_MAX_ANGLE <= a <= DESKEW_MAX_ANGLE:
                angles.append(a)
        if angles:
            angle = float(np.median(angles))

    if abs(angle) < 0.1:
        return gray

    h, w = gray.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(
        gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def quality_score(page: np.ndarray) -> float:
    """Blur variance + text-pixel ratio, blended into a 0..1 confidence."""
    gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY) if page.ndim == 3 else page
    blur_variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    blur_score = min(blur_variance / 500.0, 1.0)
    ink_ratio = float(np.mean(gray < 128))
    text_score = min(ink_ratio / 0.15, 1.0)
    return round(0.5 * blur_score + 0.5 * text_score, 4)


def _is_blank(page: np.ndarray) -> bool:
    gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY) if page.ndim == 3 else page
    ink_ratio = float(np.mean(gray < 128))
    return ink_ratio < BLANK_INK_RATIO
