"""Deterministic lab-order recommendation engine.

Rule-based only -- no LLM in this path (autonomy contract rule 6). Every
suggested test traces back to a named rule id in `packs/lab_panels.yaml`, so
`recommend_labs` is trivially explainable and reproducible for the same
inputs. `merge_with_rag` folds in whatever an LLM-backed retrieval path
(Ashwin's triage RAG) separately suggested, tagging provenance rather than
blindly trusting either side.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from app.schemas.triage import SuggestedLab
from app.services.rules.schemas import SuggestedLabOut

_PACKS_DIR = Path(__file__).resolve().parent / "packs"
_LAB_PANELS_PACK = _PACKS_DIR / "lab_panels.yaml"

_SOURCE_RANK = {"both": 0, "rule": 1, "rag": 2}


@lru_cache(maxsize=1)
def _rules() -> list[dict]:
    data = yaml.safe_load(_LAB_PANELS_PACK.read_text(encoding="utf-8")) or []
    # deterministic iteration order regardless of on-disk order changes --
    # sort by id so dedup "first rule wins the reason" is reproducible.
    return sorted(data, key=lambda r: r["id"])


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _as_set(values: list[str] | None) -> set[str]:
    return {v.strip().lower() for v in (values or []) if v and v.strip()}


def _rule_matches(
    rule: dict,
    *,
    symptoms: set[str],
    conditions: set[str],
    specialty: str,
    severity_esi: int,
    season: str | None,
    region: str | None,
    age: int | None,
    pregnant: bool,
) -> bool:
    if rule.get("fallback"):
        return False

    rule_specialties = rule.get("specialty") or []
    if rule_specialties and specialty not in rule_specialties:
        return False

    when = rule.get("when") or {}

    symptoms_any = _as_set(when.get("symptoms_any"))
    if symptoms_any and not (symptoms_any & symptoms):
        return False

    symptoms_all = _as_set(when.get("symptoms_all"))
    if symptoms_all and not symptoms_all <= symptoms:
        return False

    conditions_any = _as_set(when.get("conditions_any"))
    if conditions_any and not (conditions_any & conditions):
        return False

    if "severity_max" in when and severity_esi > when["severity_max"]:
        return False

    season_list = when.get("season")
    if season_list and season not in season_list:
        return False

    region_list = when.get("region")
    if region_list and region not in region_list:
        return False

    if "age_max" in when and (age is None or age > when["age_max"]):
        return False

    if when.get("pregnant") and not pregnant:
        return False

    # A rule with no positive match criteria at all (besides specialty) would
    # match everything, which is only intentional for the fallback -- guard
    # against an authoring mistake in the pack turning a real rule into a
    # second implicit baseline.
    if not when:
        return False

    return True


@lru_cache(maxsize=1)
def _symptom_vocabulary() -> tuple[str, ...]:
    """Every distinct `symptoms_any`/`symptoms_all` phrase across the pack,
    longest first so a substring match prefers the more specific phrase
    (e.g. "chest pain with sweating" over the bare "chest pain").
    """
    vocab: set[str] = set()
    for rule in _rules():
        when = rule.get("when") or {}
        vocab |= _as_set(when.get("symptoms_any"))
        vocab |= _as_set(when.get("symptoms_all"))
    return tuple(sorted(vocab, key=lambda s: (-len(s), s)))


def extract_symptom_keywords(*texts: str) -> list[str]:
    """Deterministic, rule-based (no LLM) keyword extraction: returns every
    pack-vocabulary symptom phrase that appears as a substring anywhere in
    `texts`. Used to turn free-text triage output (red flags, rationale) into
    the discrete `symptoms` list `recommend_labs` expects.
    """
    blob = " ".join(t.lower() for t in texts if t)
    return [phrase for phrase in _symptom_vocabulary() if phrase in blob]


def recommend_labs(
    *,
    symptoms: list[str],
    conditions: list[str],
    specialty: str,
    severity_esi: int,
    season: str | None = None,
    region: str | None = None,
    age: int | None = None,
    pregnant: bool = False,
) -> list[SuggestedLabOut]:
    """Frozen interface (section 4.2): `symptoms, conditions, specialty,
    severity_esi, season=None, region=None`. `age`/`pregnant` are additive
    optional keyword-only parameters (section 8 N2.2 lists `age_max`/
    `pregnant` as supported match keys) -- every call site that only passes
    the frozen keywords still works unchanged.
    """
    symptoms_set = _as_set(symptoms)
    conditions_set = _as_set(conditions)

    matched: dict[str, SuggestedLabOut] = {}
    any_matched = False

    for rule in _rules():
        if not _rule_matches(
            rule,
            symptoms=symptoms_set,
            conditions=conditions_set,
            specialty=specialty,
            severity_esi=severity_esi,
            season=season,
            region=region,
            age=age,
            pregnant=pregnant,
        ):
            continue
        any_matched = True
        for lab in rule["labs"]:
            key = _normalize(lab["name"])
            if key in matched:
                continue
            matched[key] = SuggestedLabOut(
                name=lab["name"],
                loinc=lab.get("loinc"),
                reason=lab["reason"],
                source="rule",
                cghs_code=rule.get("cghs_code"),
                pmjay_package=rule.get("pmjay_package"),
            )

    if not any_matched:
        baseline = next((r for r in _rules() if r.get("fallback")), None)
        if baseline is not None:
            for lab in baseline["labs"]:
                key = _normalize(lab["name"])
                matched.setdefault(
                    key,
                    SuggestedLabOut(
                        name=lab["name"],
                        loinc=lab.get("loinc"),
                        reason=lab["reason"],
                        source="rule",
                        cghs_code=baseline.get("cghs_code"),
                        pmjay_package=baseline.get("pmjay_package"),
                    ),
                )

    return sorted(matched.values(), key=lambda s: s.name)


def merge_with_rag(
    rule_labs: list[SuggestedLab], rag_labs: list[SuggestedLab]
) -> list[SuggestedLabOut]:
    """Union rule-engine and RAG-suggested labs, keyed on normalized name.
    Present in both -> `source="both"`, and the rule's `reason` wins
    (deterministic -- the rule engine is the explainable, reproducible side).
    Rule-only -> `"rule"`; RAG-only -> `"rag"`. Sorted by
    `(source_rank, name)` where `both < rule < rag`.
    """
    by_key: dict[str, SuggestedLabOut] = {}

    for lab in rule_labs:
        key = _normalize(lab.name)
        cghs = getattr(lab, "cghs_code", None)
        pmjay = getattr(lab, "pmjay_package", None)
        by_key[key] = SuggestedLabOut(
            name=lab.name, loinc=lab.loinc, reason=lab.reason, source="rule",
            cghs_code=cghs, pmjay_package=pmjay,
        )

    for lab in rag_labs:
        key = _normalize(lab.name)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = SuggestedLabOut(
                name=lab.name, loinc=lab.loinc or None, reason=lab.reason, source="rag",
            )
        else:
            # already present from the rule engine -- upgrade provenance to
            # "both", keep the rule's own (explainable) reason and coverage
            # codes, just backfill a LOINC code if the rule pack lacked one.
            by_key[key] = existing.model_copy(
                update={"source": "both", "loinc": existing.loinc or lab.loinc}
            )

    return sorted(by_key.values(), key=lambda s: (_SOURCE_RANK.get(s.source, 9), s.name))
