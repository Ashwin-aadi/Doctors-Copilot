"""Idempotent bootstrap: fetch/warm every pretrained model in the registry.

Run standalone: `python ml/download_models.py`. Never raises past main() —
each model is attempted independently, timed, and recorded into
`ml/.cache/manifest.json` as either "ok" or "unavailable" (with a reason).
An optional model failing to download is not a hard error: the script still
exits 0 so CI/bootstrap never blocks on a flaky network or a missing wheel.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
ML_DIR = REPO_ROOT / "ml"
CACHE_DIR = ML_DIR / ".cache"

os.environ.setdefault("HF_HOME", str(CACHE_DIR))
os.environ.setdefault("TRANSFORMERS_CACHE", str(CACHE_DIR))

SCISPACY_WHEELS = {
    "en_core_sci_sm": "https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_core_sci_sm-0.5.4.tar.gz",
    "en_ner_bc5cdr_md": "https://s3-us-west-2.amazonaws.com/ai2-s2-scispacy/releases/v0.5.4/en_ner_bc5cdr_md-0.5.4.tar.gz",
}


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _load_paddle_en() -> Path | None:
    from paddleocr import PaddleOCR

    PaddleOCR(lang="en", use_angle_cls=True, show_log=False)
    return Path.home() / ".paddleocr"


def _load_paddle_devanagari() -> Path | None:
    from paddleocr import PaddleOCR

    PaddleOCR(lang="devanagari", use_angle_cls=True, show_log=False)
    return Path.home() / ".paddleocr"


def _check_tesseract() -> Path | None:
    import pytesseract

    pytesseract.get_tesseract_version()
    return None


def _load_scispacy(pkg: str) -> Path | None:
    import importlib
    import subprocess

    try:
        mod = importlib.import_module(pkg)
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", SCISPACY_WHEELS[pkg]],
            check=True,
            timeout=600,
        )
        mod = importlib.import_module(pkg)
    model_path = Path(mod.__file__).resolve().parent
    return model_path


def _load_hf_biomedical_ner() -> Path | None:
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    name = "d4data/biomedical-ner-all"
    AutoTokenizer.from_pretrained(name, cache_dir=CACHE_DIR)
    AutoModelForTokenClassification.from_pretrained(name, cache_dir=CACHE_DIR)
    return CACHE_DIR


def _check_negspacy() -> Path | None:
    import negspacy  # noqa: F401

    return None


MODELS: list[tuple[str, bool, Callable[[], Path | None]]] = [
    ("paddleocr_en", True, _load_paddle_en),
    ("paddleocr_devanagari", True, _load_paddle_devanagari),
    ("tesseract", False, _check_tesseract),
    ("en_core_sci_sm", True, lambda: _load_scispacy("en_core_sci_sm")),
    ("en_ner_bc5cdr_md", True, lambda: _load_scispacy("en_ner_bc5cdr_md")),
    ("hf_biomedical_ner_all", True, _load_hf_biomedical_ner),
    ("negspacy", False, _check_negspacy),
]


def bootstrap() -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = CACHE_DIR / "manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError):
            manifest = {}

    for name, optional, loader in MODELS:
        start = time.monotonic()
        try:
            path = loader()
            elapsed = time.monotonic() - start
            size = _dir_size(path) if path else 0
            manifest[name] = {
                "status": "ok",
                "size_bytes": size,
                "elapsed_s": round(elapsed, 2),
            }
            print(f"[ok]          {name:24s} size={size:>12,d}B  elapsed={elapsed:.2f}s")
        except Exception as exc:  # noqa: BLE001 - any model may be missing/offline
            elapsed = time.monotonic() - start
            manifest[name] = {
                "status": "unavailable",
                "reason": f"{type(exc).__name__}: {exc}",
                "elapsed_s": round(elapsed, 2),
            }
            severity = "optional" if optional else "required-fallback"
            print(f"[unavailable] {name:24s} ({severity}) elapsed={elapsed:.2f}s :: {exc}")

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"\nmanifest written: {manifest_path}")
    return manifest


def main() -> int:
    bootstrap()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
