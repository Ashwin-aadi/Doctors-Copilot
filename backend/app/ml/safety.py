"""Drug interaction / allergy / contraindication safety engine.

`check_interactions` normalizes each medication to an ingredient (+RxCUI via
`app.ml.ner`), queries every unordered pair against the `interactions` table
in `ml/data/interactions.db` (built by `app.ml.kb_build`), cross-checks
allergies (direct name, ingredient, and cross-class via
`ml/data/allergy_classes.yaml`), and matches conditions against
`contraindications`. Every finding must carry a real `evidence_source`/`url`
or it is dropped -- there is no such thing as an unsourced safety finding
here.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.ml.ner import brand_to_generic, resolve_rxcui
from app.ml.schemas_ml import InteractionRequest
from app.schemas.ml import AllergyConflict, Contraindication, InteractionPair, InteractionReport

DATA_DIR = Path(__file__).resolve().parents[3] / "ml" / "data"
DB_PATH = DATA_DIR / "interactions.db"

SEVERITY_RANK = {"major": 3, "moderate": 2, "minor": 1}

_ALLERGY_CLASSES: dict[str, dict] | None = None


def _load_allergy_classes() -> dict[str, dict]:
    global _ALLERGY_CLASSES
    if _ALLERGY_CLASSES is not None:
        return _ALLERGY_CLASSES
    path = DATA_DIR / "allergy_classes.yaml"
    if not path.exists():
        _ALLERGY_CLASSES = {}
    else:
        with path.open(encoding="utf-8") as f:
            _ALLERGY_CLASSES = yaml.safe_load(f) or {}
    return _ALLERGY_CLASSES


def _normalize(name: str) -> tuple[str, str | None]:
    generic = brand_to_generic(name)
    return generic, resolve_rxcui(generic)


def _db_connect() -> sqlite3.Connection | None:
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(DB_PATH)


def _find_pair(conn: sqlite3.Connection, name_a: str, name_b: str) -> dict | None:
    row = conn.execute(
        "SELECT severity, mechanism, source, url, rxcui_a, rxcui_b, name_a, name_b FROM interactions "
        "WHERE (LOWER(name_a)=? AND LOWER(name_b)=?) OR (LOWER(name_a)=? AND LOWER(name_b)=?)",
        (name_a.lower(), name_b.lower(), name_b.lower(), name_a.lower()),
    ).fetchone()
    if row is None:
        return None
    severity, mechanism, source, url, rxcui_a, rxcui_b, db_name_a, db_name_b = row
    return {
        "severity": severity,
        "mechanism": mechanism,
        "source": source,
        "url": url,
    }


def _allergy_conflict(allergen: str, drug_generic: str) -> tuple[str, str] | None:
    """Returns (rationale, source) if `drug_generic` conflicts with `allergen`."""
    allergen_l = allergen.strip().lower()
    drug_l = drug_generic.strip().lower()
    if allergen_l == drug_l or allergen_l in drug_l.split("+"):
        return f"Direct match: patient is allergic to {allergen}.", "direct-name-match"

    classes = _load_allergy_classes()
    entry = classes.get(allergen_l)
    if entry and drug_l in {c.lower() for c in entry.get("cross_reacts", [])}:
        return entry.get("rationale", f"Cross-reactivity between {allergen} and {drug_generic}."), (
            "allergy_classes.yaml (cross-class rule)"
        )
    # Also check the reverse: is the allergen itself a class name that lists drug_l,
    # or is drug_l a class whose cross-reacts include the allergen.
    for class_name, class_entry in classes.items():
        cross = {c.lower() for c in class_entry.get("cross_reacts", [])}
        if allergen_l in cross and drug_l == class_name.lower():
            return class_entry.get("rationale", ""), "allergy_classes.yaml (cross-class rule)"
    return None


async def check_interactions(req: InteractionRequest) -> InteractionReport:
    conn = _db_connect()

    normalized_meds = [(med, *_normalize(med)) for med in req.medications]

    pairs: list[InteractionPair] = []
    seen_ingredient_pairs: set[frozenset[str]] = set()
    if conn is not None:
        for i in range(len(normalized_meds)):
            for j in range(i + 1, len(normalized_meds)):
                med_a, generic_a, rxcui_a = normalized_meds[i]
                med_b, generic_b, rxcui_b = normalized_meds[j]
                key = frozenset((generic_a.lower(), generic_b.lower()))
                if key in seen_ingredient_pairs:
                    continue
                found = _find_pair(conn, generic_a, generic_b)
                if found is None:
                    continue
                seen_ingredient_pairs.add(key)
                pairs.append(
                    InteractionPair(
                        drug_a=med_a,
                        rxcui_a=rxcui_a,
                        drug_b=med_b,
                        rxcui_b=rxcui_b,
                        severity=found["severity"],
                        mechanism=found["mechanism"],
                        evidence_source=found["source"],
                        url=found["url"],
                    )
                )

    pairs = [p for p in pairs if p.url]
    pairs.sort(key=lambda p: (-SEVERITY_RANK.get(p.severity, 0), p.drug_a, p.drug_b))

    allergy_conflicts: list[AllergyConflict] = []
    for allergy in req.allergies:
        for med, generic, rxcui in normalized_meds:
            conflict = _allergy_conflict(allergy, generic)
            if conflict is None:
                continue
            rationale, source = conflict
            allergy_conflicts.append(
                AllergyConflict(
                    allergen=allergy,
                    drug=med,
                    rxcui=rxcui,
                    rationale=rationale,
                    source=source,
                )
            )

    contraindications: list[Contraindication] = []
    if conn is None:
        conn = _db_connect()
    if conn is not None:
        for condition in req.conditions:
            for med, generic, _rxcui in normalized_meds:
                row = conn.execute(
                    "SELECT text, url FROM contraindications WHERE LOWER(ingredient)=? "
                    "AND (LOWER(condition)=? OR LOWER(text) LIKE ?)",
                    (generic.lower(), condition.lower(), f"%{condition.lower()}%"),
                ).fetchone()
                if row is None:
                    continue
                text, url = row
                if not url:
                    continue
                contraindications.append(
                    Contraindication(
                        drug=med,
                        condition=condition,
                        rationale=text,
                        source=url,
                    )
                )
        conn.close()

    return InteractionReport(
        pairs=pairs,
        allergy_conflicts=allergy_conflicts,
        contraindications=contraindications,
        generated_at=datetime.now(UTC),
    )
