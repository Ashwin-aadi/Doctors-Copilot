"""Medication candidate ranking.

`suggest_medications` retrieves indication candidates from the
`indications_fts` BM25 index over `label_sections` (both built by
`app.ml.kb_build` from openFDA `indications_and_usage` text), hard-filters
anything that would trigger an allergy conflict or a `major` interaction
with the patient's current medications via `app.ml.safety`, flags
`moderate` interactions and renal/hepatic/pregnancy cautions from label
`warnings` text, then ranks by indication match, fewest flags, and NLEM /
Jan Aushadhi availability in India.

India availability is read directly from `india_drugs.csv` keyed by
*ingredient* (Niyati's `app.services.mapping.india_drugs.to_generic` only
resolves the other direction -- brand/rxcui -> ingredient -- so it can't
answer "what Indian brands exist for this ingredient").
"""

from __future__ import annotations

import csv
import re
import sqlite3
from functools import lru_cache
from pathlib import Path

from app.ml.ner import resolve_rxcui
from app.ml.safety import check_interactions
from app.ml.schemas_ml import InteractionRequest, MedSuggestRequest
from app.schemas.ml import MedCandidate

DATA_DIR = Path(__file__).resolve().parents[3] / "ml" / "data"
DB_PATH = DATA_DIR / "interactions.db"
INDIA_DRUGS_CSV = (
    Path(__file__).resolve().parents[1] / "services" / "mapping" / "data" / "india_drugs.csv"
)

MAX_CANDIDATES = 10
_MANDATORY_RATIONALE = "This is decision support requiring doctor approval."
_FTS_SANITIZE_RE = re.compile(r"[^a-z0-9 ]+")

# A differential arrives as a sentence -- "Renal colic (ureteric stone) -
# considered given urology triage and need for imaging". Only the head names
# the condition; the rest explains the reasoning and is pure noise to a
# full-text search over drug labels.
_CONDITION_TAIL_RE = re.compile(r"\s+[-–—:(]|\s+(?:supported|considered|possible|plausible|likely|given|due)")

# Words that appear in nearly every drug label. OR-ing them in was what made
# every condition return the same handful of high-frequency labels regardless
# of what was actually asked.
_STOPWORDS = frozenset(
    """a an and are as at be by for from given in into is it its of on or that the their then
    there these this to was were will with need needs needed patient patients adult adults
    treatment treat therapy use used using indicated indication management care clinical
    symptoms symptom signs detect detection marker markers evaluation evaluate assess
    warrants without with less more likely possible plausible considered supported due
    presenting present history risk""".split()
)


@lru_cache(maxsize=1)
def _india_rows() -> list[dict]:
    if not INDIA_DRUGS_CSV.exists():
        return []
    with INDIA_DRUGS_CSV.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _india_lookup(ingredient: str) -> dict:
    ingredient_l = ingredient.strip().lower()
    rows = [r for r in _india_rows() if r.get("ingredient", "").strip().lower() == ingredient_l]
    if not rows:
        return {"nlem": False, "jan_aushadhi": False, "brand": None, "mrp_inr": None}
    nlem = any(r.get("nlem", "").strip().lower() in ("1", "true", "yes") for r in rows)
    ja_rows = [r for r in rows if r.get("jan_aushadhi_code")]
    mrps = [float(r["mrp_inr"]) for r in rows if r.get("mrp_inr")]
    brand = ja_rows[0]["brand"] if ja_rows else rows[0]["brand"]
    return {
        "nlem": nlem,
        "jan_aushadhi": bool(ja_rows),
        "brand": brand,
        "mrp_inr": min(mrps) if mrps else None,
    }


def _db_connect() -> sqlite3.Connection | None:
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(DB_PATH)


def _condition_terms(condition: str) -> list[str]:
    """The content words that actually name the condition."""
    head = _CONDITION_TAIL_RE.split(condition.strip(), maxsplit=1)[0]
    words = _FTS_SANITIZE_RE.sub(" ", head.lower()).split()
    return [w for w in words if w not in _STOPWORDS and len(w) > 2]


def _condition_label(condition: str) -> str:
    """The condition as it should read on a suggestion card: the name only,
    without the differential's trailing reasoning."""
    head = _CONDITION_TAIL_RE.split(condition.strip(), maxsplit=1)[0].strip(" .,;:-")
    return head or condition.strip()


def _fts_query(condition: str) -> str:
    """FTS5 treats space-separated terms as AND, which is the point: a label
    has to mention every word of the condition, not any one of them."""
    terms = _condition_terms(condition)
    return " ".join(terms) if terms else _FTS_SANITIZE_RE.sub(" ", condition.lower()).strip()


def _label_url(conn: sqlite3.Connection, ingredient: str) -> str:
    row = conn.execute(
        "SELECT url FROM label_sections WHERE ingredient=? AND section='indications_and_usage' LIMIT 1",
        (ingredient,),
    ).fetchone()
    return row[0] if row else ""


def _label_text(conn: sqlite3.Connection, ingredient: str, section: str) -> str:
    row = conn.execute(
        "SELECT text FROM label_sections WHERE ingredient=? AND section=? LIMIT 1",
        (ingredient, section),
    ).fetchone()
    return row[0] if row else ""


def _retrieve_candidates(conn: sqlite3.Connection, condition: str) -> list[tuple[str, float, str]]:
    """Returns deduped `(ingredient, indication_match[0-1], indications_text)`, best first."""
    rows: list[tuple[str, str]] = []
    try:
        rows = [
            (ingredient, text)
            for ingredient, _score, text in conn.execute(
                "SELECT ingredient, bm25(indications_fts) AS score, text FROM indications_fts "
                "WHERE indications_fts MATCH ? ORDER BY score LIMIT 20",
                (_fts_query(condition),),
            ).fetchall()
        ]
    except sqlite3.OperationalError:
        rows = []

    if not rows:
        like_term = f"%{condition.lower()}%"
        rows = conn.execute(
            "SELECT ingredient, text FROM label_sections "
            "WHERE section='indications_and_usage' AND LOWER(text) LIKE ?",
            (like_term,),
        ).fetchall()

    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for ingredient, text in rows:
        if ingredient in seen:
            continue
        seen.add(ingredient)
        deduped.append((ingredient, text))

    n = len(deduped)
    out: list[tuple[str, float, str]] = []
    for idx, (ingredient, text) in enumerate(deduped):
        match = 0.6 if n <= 1 else max(0.3, round(1.0 - idx * 0.6 / (n - 1), 3))
        out.append((ingredient, match, text))
    return out


async def suggest_medications(req: MedSuggestRequest) -> list[MedCandidate]:
    conn = _db_connect()
    if conn is None:
        return []

    # Keep the condition each candidate was actually retrieved for. Naming
    # every condition on every card made all the rationales identical and told
    # the doctor nothing about why this drug was suggested.
    raw: dict[str, tuple[float, str, str]] = {}
    for condition in req.conditions:
        matched_for = _condition_label(condition)
        for ingredient, match, text in _retrieve_candidates(conn, condition):
            existing = raw.get(ingredient)
            if existing is None or match > existing[0]:
                raw[ingredient] = (match, text, matched_for)

    if not raw:
        conn.close()
        return []

    candidates: list[MedCandidate] = []
    for ingredient, (match, _indications_text, matched_for) in raw.items():
        check_meds = [*req.current_medications, ingredient]
        report = await check_interactions(
            InteractionRequest(medications=check_meds, allergies=req.allergies, conditions=[])
        )

        allergy_conflict = any(ac.drug.lower() == ingredient.lower() for ac in report.allergy_conflicts)
        major_interaction = any(
            pair.severity == "major"
            and ingredient.lower() in (pair.drug_a.lower(), pair.drug_b.lower())
            for pair in report.pairs
        )
        if allergy_conflict or major_interaction:
            continue

        safety_flags: list[str] = []
        for pair in report.pairs:
            if pair.severity == "moderate" and ingredient.lower() in (
                pair.drug_a.lower(),
                pair.drug_b.lower(),
            ):
                other = pair.drug_b if pair.drug_a.lower() == ingredient.lower() else pair.drug_a
                safety_flags.append(f"moderate interaction with {other}")

        warnings_text = _label_text(conn, ingredient, "warnings").lower()
        if req.renal_impairment and "renal impairment" in warnings_text:
            safety_flags.append("renal impairment caution")
        if req.hepatic_impairment and "hepatic impairment" in warnings_text:
            safety_flags.append("hepatic impairment caution")
        if "pregnan" in warnings_text:
            safety_flags.append("pregnancy caution")

        india = _india_lookup(ingredient)
        rationale_parts = [f"Label lists an indication for {matched_for}."]
        if india.get("brand"):
            rationale_parts.append(f"Commonly available in India as {india['brand']}.")
        rationale_parts.append(_MANDATORY_RATIONALE)

        candidates.append(
            MedCandidate(
                name=ingredient.title(),
                rxcui=resolve_rxcui(ingredient),
                ingredient=ingredient,
                indication_match=match,
                safety_flags=safety_flags,
                rationale=" ".join(rationale_parts),
                source_url=_label_url(conn, ingredient) or None,
                nlem_listed=bool(india.get("nlem")),
                jan_aushadhi_available=bool(india.get("jan_aushadhi")),
                mrp_inr=india.get("mrp_inr"),
            )
        )

    conn.close()
    candidates.sort(
        key=lambda c: (-c.indication_match, len(c.safety_flags), 0 if c.nlem_listed else 1, c.name)
    )
    return candidates[:MAX_CANDIDATES]
