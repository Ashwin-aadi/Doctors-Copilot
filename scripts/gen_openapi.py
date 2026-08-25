#!/usr/bin/env python
"""Dump the FastAPI OpenAPI schema to openapi.json at the repo root."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402

if __name__ == "__main__":
    schema = app.openapi()
    out_path = ROOT / "openapi.json"
    out_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"wrote {out_path} ({len(schema.get('paths', {}))} paths)")
