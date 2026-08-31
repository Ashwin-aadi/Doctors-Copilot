"""Lab report parser: turn an OcrResult into a deduped list of LabResultOut.

Two extraction modes run over every page and are merged:

1. Table mode -- find a header row inside `page["tables"]` by fuzzy-matching
   its cells against role keywords (test/result/unit/reference), then reads
   the following rows positionally by column index.
2. Line mode -- regex over `page["text"]`, for reports where table
   clustering didn't recover a clean grid (e.g. dense multi-column OCR
   noise).

Both modes resolve the raw test name to a canonical name via
`ml/data/test_aliases.yaml` (rapidfuzz, score >= 80) and fall back to
`ml/data/reference_ranges.yaml` for the normal range only when the report
itself didn't print one. See docs/DECISIONS.md for why per-cell confidence
is a page-level proxy rather than true per-cell OCR confidence.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from rapidfuzz import fuzz, process

from app.ml.ocr import OcrResult
from app.schemas.document import LabResultOut

DATA_DIR = Path(__file__).resolve().parents[3] / "ml" / "data"
# WRatio rewards a shared leading token, so at 80 "Total Testosterone" matched
# "Total Leukocyte Count (TLC)" at 85.5 and was recorded as a white-cell count.
# Every legitimate alias on the Indian report templates this parses scores 90+
# (almost all exactly 100); the dangerous near-misses sit at 80-86.
ALIAS_MATCH_THRESHOLD = 90

# Below this length a name carries too little signal to fuzzy-match safely:
# "LH" scores 80 against "LDH" and they are unrelated analytes. Short names
# must match an alias exactly.
EXACT_ONLY_NAME_LENGTH = 4
HEADER_MATCH_THRESHOLD = 80
CRITICAL_RANGE_MULTIPLIER = 1.5

ROLE_KEYWORDS: dict[str, list[str]] = {
    "name": ["test", "investigation", "parameter"],
    "value": ["result", "value"],
    "unit": ["unit", "units"],
    "range": ["reference", "normal", "range"],
}

LINE_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 ()\-/\.]{2,40})[\s\.:]{2,}"
    r"(?P<value>[<>]?\d+\.?\d*)\s*(?P<unit>[A-Za-zµ%/\^0-9]{1,12})?\s*"
    r"(?:[\(\[]?(?P<low>\d+\.?\d*)\s*[-–]\s*(?P<high>\d+\.?\d*)[\)\]]?)?"
)

# Ranges are printed with thousands separators as often as not ("4,000 -
# 11,000"). Without the comma branch the regex matched from inside the group
# and read that as 0-11, turning a normal white-cell count into a critical one.
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
RANGE_RE = re.compile(rf"(?P<low>{_NUM})\s*[-–]\s*(?P<high>{_NUM})")
GT_RE = re.compile(rf"[>≥]\s*(?P<low>{_NUM})")
LT_RE = re.compile(rf"[<≤]\s*(?P<high>{_NUM})")


def _load_yaml(name: str) -> Any:
    with (DATA_DIR / name).open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_alias_index() -> dict[str, str]:
    aliases = _load_yaml("test_aliases.yaml")
    index: dict[str, str] = {}
    for canonical, entry in aliases.items():
        index[canonical.replace("_", " ")] = canonical
        for alias in entry.get("aliases", []):
            index[alias] = canonical
    return index


_ALIAS_INDEX = _build_alias_index()
_ALIAS_CHOICES = list(_ALIAS_INDEX.keys())
_REFERENCE_RANGES = _load_yaml("reference_ranges.yaml")
_CRITICAL_RULES = _load_yaml("critical_rules.yaml")


def _normalise_name(raw: str) -> str:
    """Casefold and drop punctuation, so "SGPT (ALT)" and "sgpt alt" agree."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", raw.lower()).split())


_EXACT_INDEX: dict[str, str] = {_normalise_name(a): c for a, c in _ALIAS_INDEX.items()}


def _match_canonical(raw_name: str) -> tuple[str, float] | None:
    raw_name = raw_name.strip()
    if not raw_name:
        return None

    # An exact alias always wins, and is the only thing trusted for a name too
    # short to fuzzy-match safely.
    exact = _EXACT_INDEX.get(_normalise_name(raw_name))
    if exact is not None:
        return exact, 1.0
    if len(_normalise_name(raw_name).replace(" ", "")) <= EXACT_ONLY_NAME_LENGTH:
        return None

    match = process.extractOne(raw_name, _ALIAS_CHOICES, scorer=fuzz.WRatio)
    if match is None or match[1] < ALIAS_MATCH_THRESHOLD:
        return None
    alias, score, _idx = match
    return _ALIAS_INDEX[alias], score / 100.0


def _num(raw: str) -> float:
    return float(raw.replace(",", ""))


def _parse_range(text: str) -> tuple[float | None, float | None]:
    text = text.strip()
    m = RANGE_RE.search(text)
    if m:
        return _num(m.group("low")), _num(m.group("high"))
    m = GT_RE.search(text)
    if m:
        return _num(m.group("low")), None
    m = LT_RE.search(text)
    if m:
        return None, _num(m.group("high"))
    return None, None


def _default_range(canonical_name: str) -> tuple[float | None, float | None, str | None]:
    entry = _REFERENCE_RANGES.get(canonical_name)
    if not entry:
        return None, None, None
    default = entry.get("default", {})
    return default.get("low"), default.get("high"), entry.get("unit")


def _to_rule_unit(value: float, unit: str | None, rule_unit: str) -> float | None:
    if unit is None:
        return None
    u = unit.strip().lower().replace(" ", "")
    ru = rule_unit.strip().lower().replace(" ", "")
    if u == ru:
        return value
    if ru == "/ul":
        if "lakh" in u:
            return value * 100_000
        if u in {"cells/cumm", "/cumm", "/mm3", "cumm"}:
            return value
    return None


def _hard_critical(canonical_name: str, value: float, unit: str | None) -> bool:
    rule = _CRITICAL_RULES.get(canonical_name)
    if not rule:
        return False
    converted = _to_rule_unit(value, unit, rule["unit"])
    if converted is None:
        return False
    if rule["operator"] == "<":
        return converted < rule["threshold"]
    if rule["operator"] == ">":
        return converted > rule["threshold"]
    return False


def _generic_critical(value: float, low: float | None, high: float | None) -> bool:
    if low is None or high is None:
        return False
    width = high - low
    if width <= 0:
        return False
    if value > high:
        return (value - high) > CRITICAL_RANGE_MULTIPLIER * width
    if value < low:
        return (low - value) > CRITICAL_RANGE_MULTIPLIER * width
    return False


def _flag(
    canonical_name: str, value: float, unit: str | None, low: float | None, high: float | None
) -> str:
    if low is None and high is None:
        base = "unknown"
    elif low is not None and value < low:
        base = "low"
    elif high is not None and value > high:
        base = "high"
    else:
        base = "normal"

    if base != "unknown" and (
        _generic_critical(value, low, high) or _hard_critical(canonical_name, value, unit)
    ):
        return "critical"
    return base


def _page_mean_conf(page: dict[str, Any]) -> float:
    confs = [b["conf"] for b in page["blocks"]]
    return sum(confs) / len(confs) if confs else 0.5


def _block_conf_lookup(page: dict[str, Any]) -> dict[str, float]:
    return {b["text"].strip(): b["conf"] for b in page["blocks"]}


def _row_conf(cells: list[str], conf_by_text: dict[str, float], fallback: float) -> float:
    confs = [conf_by_text[c.strip()] for c in cells if c.strip() in conf_by_text]
    return sum(confs) / len(confs) if confs else fallback


# A result cell as most labs actually print it: the number, optionally with its
# unit right beside it ("13.8 g/dL", "3,400 /uL", "<0.5 mg/dL"). Splitting the
# two here is what lets a report with no separate Unit column be read at all --
# requiring a bare number silently dropped every such row, which is to say most
# real reports.
_VALUE_UNIT_RE = re.compile(
    r"^[<>≤≥]?\s*(?P<value>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(?P<unit>[A-Za-zµ%/\^0-9\.\-]{1,15})?"
)


def _split_value_unit(raw: str) -> tuple[float | None, str | None]:
    m = _VALUE_UNIT_RE.match(raw.strip())
    if m is None:
        return None, None
    try:
        value = float(m.group("value").replace(",", ""))
    except ValueError:
        return None, None
    unit = (m.group("unit") or "").strip() or None
    return value, unit


def _parse_value(raw: str) -> float | None:
    return _split_value_unit(raw)[0]


def _find_header(table: list[list[str]]) -> tuple[int, dict[int, str]] | None:
    for row_idx, row in enumerate(table):
        roles: dict[int, str] = {}
        for col_idx, cell in enumerate(row):
            cell_l = cell.strip().lower()
            if not cell_l:
                continue
            best_role, best_score = None, 0.0
            for role, keywords in ROLE_KEYWORDS.items():
                score = max(fuzz.WRatio(cell_l, kw) for kw in keywords)
                if score > best_score:
                    best_role, best_score = role, score
            if best_score >= HEADER_MATCH_THRESHOLD:
                roles[col_idx] = best_role
        if "name" in roles.values() and "value" in roles.values():
            return row_idx, roles
    return None


def _table_mode_entries(
    page: dict[str, Any], page_idx: int, conf_by_text: dict[str, float], fallback_conf: float
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for table in page.get("tables", []):
        header = _find_header(table)
        if header is None:
            continue
        header_row_idx, roles = header
        name_col = next((c for c, r in roles.items() if r == "name"), None)
        value_col = next((c for c, r in roles.items() if r == "value"), None)
        unit_col = next((c for c, r in roles.items() if r == "unit"), None)
        range_col = next((c for c, r in roles.items() if r == "range"), None)
        if name_col is None or value_col is None:
            continue

        for row in table[header_row_idx + 1 :]:
            if len(row) <= max(name_col, value_col):
                continue
            raw_name = row[name_col]
            value, inline_unit = _split_value_unit(row[value_col])
            if value is None:
                continue
            match = _match_canonical(raw_name)
            if match is None:
                continue
            canonical_name, alias_score = match
            unit = row[unit_col].strip() if unit_col is not None and unit_col < len(row) else None
            # A dedicated Unit column wins; otherwise take what was printed
            # alongside the value.
            unit = unit or inline_unit
            low, high = (
                _parse_range(row[range_col]) if range_col is not None and range_col < len(row) else (None, None)
            )
            if low is None and high is None:
                low, high, default_unit = _default_range(canonical_name)
                unit = unit or default_unit
            conf = min(_row_conf(row, conf_by_text, fallback_conf), alias_score)
            entries.append(
                {
                    "test_name": raw_name.strip(),
                    "normalized_name": canonical_name,
                    "value": value,
                    "unit": unit or None,
                    "ref_low": low,
                    "ref_high": high,
                    "flag": _flag(canonical_name, value, unit, low, high),
                    "confidence": conf,
                    "page": page_idx + 1,
                }
            )
    return entries


def _line_mode_entries(
    page: dict[str, Any], page_idx: int, fallback_conf: float
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in page["text"].splitlines():
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        value = _parse_value(m.group("value"))
        if value is None:
            continue
        match = _match_canonical(m.group("name"))
        if match is None:
            continue
        canonical_name, alias_score = match
        unit = m.group("unit")
        low = float(m.group("low")) if m.group("low") else None
        high = float(m.group("high")) if m.group("high") else None
        if low is None and high is None:
            low, high, default_unit = _default_range(canonical_name)
            unit = unit or default_unit
        conf = min(fallback_conf, alias_score)
        entries.append(
            {
                "test_name": m.group("name").strip(),
                "normalized_name": canonical_name,
                "value": value,
                "unit": unit,
                "ref_low": low,
                "ref_high": high,
                "flag": _flag(canonical_name, value, unit, low, high),
                "confidence": conf,
                "page": page_idx + 1,
            }
        )
    return entries


# A value on its own line: "4.72", "<0.5", "11,800".
_STACKED_VALUE_RE = re.compile(rf"^[<>]?\s*(?:{_NUM})$")
# A unit on its own line: "ng/mL", "cells/cu mm", "%".
_STACKED_UNIT_RE = re.compile(r"^[A-Za-zµ%][A-Za-zµ%/\^0-9\. ]{0,14}$")


def _stacked_mode_entries(
    page: dict[str, Any], page_idx: int, fallback_conf: float
) -> list[dict[str, Any]]:
    """Read a results table that arrived one cell per line.

    Extracting text from a PDF whose results are laid out in a table gives back
    every cell on its own line -- name, then value, then reference interval,
    then unit -- with nothing left on the line to anchor a name-value pair to.
    `_line_mode_entries` needs both on one line and `_table_mode_entries` needs
    geometry the text-only path never produces, so a perfectly clean digital
    lab report parsed to nothing at all.

    A row is recognised as a known test name on one line followed by a bare
    number on the next; an interval and a unit are taken from the two lines
    after it when they look like one. Requiring the name to resolve to a
    canonical test is what keeps this from reading prose as results.
    """
    lines = [ln.strip() for ln in page["text"].splitlines()]
    entries: list[dict[str, Any]] = []

    for i, line in enumerate(lines[:-1]):
        if not line or _STACKED_VALUE_RE.match(line):
            continue
        value = _parse_value(lines[i + 1])
        if value is None or not _STACKED_VALUE_RE.match(lines[i + 1]):
            continue
        match = _match_canonical(line)
        if match is None:
            continue
        canonical_name, alias_score = match

        low = high = None
        unit = None
        # The interval and unit follow the value, in either order on some
        # templates; only the two lines after it are considered, so a value
        # from the next row can never be read as this row's range.
        for candidate in lines[i + 2 : i + 4]:
            if not candidate:
                continue
            if low is None and high is None:
                parsed_low, parsed_high = _parse_range(candidate)
                if parsed_low is not None or parsed_high is not None:
                    low, high = parsed_low, parsed_high
                    continue
            if unit is None and _STACKED_UNIT_RE.match(candidate):
                unit = candidate

        if low is None and high is None:
            low, high, default_unit = _default_range(canonical_name)
            unit = unit or default_unit

        entries.append(
            {
                "test_name": line,
                "normalized_name": canonical_name,
                "value": value,
                "unit": unit,
                "ref_low": low,
                "ref_high": high,
                "flag": _flag(canonical_name, value, unit, low, high),
                "confidence": min(fallback_conf, alias_score),
                "page": page_idx + 1,
            }
        )
    return entries


def parse_labs(ocr: OcrResult) -> list[LabResultOut]:
    all_entries: list[dict[str, Any]] = []
    for page_idx, page in enumerate(ocr["pages"]):
        fallback_conf = _page_mean_conf(page)
        conf_by_text = _block_conf_lookup(page)
        all_entries.extend(_table_mode_entries(page, page_idx, conf_by_text, fallback_conf))
        all_entries.extend(_line_mode_entries(page, page_idx, fallback_conf))
        all_entries.extend(_stacked_mode_entries(page, page_idx, fallback_conf))

    best_by_name: dict[str, dict[str, Any]] = {}
    for entry in all_entries:
        existing = best_by_name.get(entry["normalized_name"])
        if existing is None or entry["confidence"] > existing["confidence"]:
            best_by_name[entry["normalized_name"]] = entry

    return [LabResultOut(**entry) for entry in best_by_name.values()]
