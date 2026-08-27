"""Lab-order rules engine tests. The pack/pure-function tests need no DB at
all; `test_recommend_lab_order_api_*` needs a reachable Postgres (same infra
caveat as the rest of `tests/services/`) since it creates a `Visit` row and
calls the real route.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
import yaml
from sqlalchemy import delete

from app.db.models.clinical import LabOrder, Visit
from app.db.session import SessionLocal
from app.schemas.triage import SuggestedLab
from app.services.rules.lab_rules import extract_symptom_keywords, merge_with_rag, recommend_labs
from tests.services.conftest import patient_id

# Resolved from this file, not the working directory: `make test` runs
# pytest with `backend/` as cwd, so a repo-root-relative path never
# resolves. Mirrors how app/rag/triage_rag.py locates its own data dir.
_BACKEND = Path(__file__).resolve().parents[2]
_PACK_PATH = _BACKEND / "app/services/rules/packs/lab_panels.yaml"


def test_pack_has_at_least_30_rules_and_mandatory_coverage():
    rules = yaml.safe_load(open(_PACK_PATH, encoding="utf-8"))
    assert len(rules) >= 30, len(rules)
    ids = {r["id"] for r in rules}
    assert "general_baseline" in ids
    must_cover = ["tb", "dengue", "malaria", "anaemia", "diabet", "anc", "snake"]
    for term in must_cover:
        assert any(term in rule_id for rule_id in ids), term


def test_recommend_labs_matches_monsoon_fever_and_dedupes():
    labs = recommend_labs(
        symptoms=["fever", "chills", "body ache"],
        conditions=[],
        specialty="general_medicine",
        severity_esi=3,
        season="monsoon",
    )
    names = {lab.name for lab in labs}
    assert "Dengue NS1 antigen" in names
    assert "Malaria rapid test (Pf/Pv)" in names
    # every returned item traces to a real rule, tagged as such
    assert all(lab.source == "rule" for lab in labs)
    # no duplicate names even though multiple rules can suggest CBC etc.
    assert len(names) == len(labs)


def test_recommend_labs_snakebite_returns_coagulation_panel():
    labs = recommend_labs(
        symptoms=["snakebite", "bleeding gums"],
        conditions=[],
        specialty="emergency_medicine",
        severity_esi=2,
    )
    names = {lab.name for lab in labs}
    assert any("clotting" in n.lower() or "coagulation" in n.lower() for n in names)


def test_recommend_labs_anc_first_visit_pregnant():
    labs = recommend_labs(
        symptoms=[],
        conditions=["pregnant"],
        specialty="obstetrics_gynaecology",
        severity_esi=5,
        pregnant=True,
    )
    names = {lab.name for lab in labs}
    for expected in ("Haemoglobin", "HBsAg", "VDRL / RPR (syphilis)"):
        assert expected in names


def test_recommend_labs_falls_back_to_general_baseline_when_nothing_matches():
    labs = recommend_labs(
        symptoms=["a symptom nothing in the pack matches"],
        conditions=[],
        specialty="general_medicine",
        severity_esi=5,
    )
    names = {lab.name for lab in labs}
    assert names == {"CBC", "Random blood sugar (RBS)", "Urine routine"}


def test_merge_with_rag_tags_provenance_and_orders_both_first():
    rule_labs = recommend_labs(
        symptoms=["fever", "chills"], conditions=[], specialty="general_medicine",
        severity_esi=3, season="monsoon",
    )
    rag_labs = [
        SuggestedLab(name="CBC with platelet count", loinc=None, reason="RAG suggestion", source="rag"),
        SuggestedLab(name="Vitamin D", loinc=None, reason="RAG-only suggestion", source="rag"),
    ]
    merged = merge_with_rag(rule_labs, rag_labs)
    by_name = {m.name: m for m in merged}
    assert by_name["CBC with platelet count"].source == "both"
    assert by_name["Vitamin D"].source == "rag"
    sources_in_order = [m.source for m in merged]
    assert sources_in_order.index("both") < sources_in_order.index("rag")


def test_extract_symptom_keywords_finds_pack_vocabulary_in_free_text():
    keywords = extract_symptom_keywords("pattern match: (snake|serpent) ?bite", "patient reports fever and chills")
    assert "fever" in keywords
    assert "chills" in keywords


@pytest_asyncio.fixture
async def _clean_lab_orders():
    """Clear only the queue/lab-order/visit rows this module's fixture
    patients own.

    These wipes were unscoped (`delete(Visit)` with no WHERE), so running the
    full suite destroyed the seeded demo visit and every other module's
    fixtures along with them -- `tests/integration/test_visit_flow.py` failed
    on whatever ran after this file and passed on its own. Scoping to the
    Chennai fixture patients keeps the clean slate this module needs without
    reaching into anyone else's rows.
    """

    ours = [patient_id(i) for i in range(1, 9)]

    async def _wipe() -> None:
        async with SessionLocal() as session:
            await session.execute(delete(LabOrder).where(LabOrder.patient_id.in_(ours)))
            await session.execute(delete(Visit).where(Visit.patient_id.in_(ours)))
            await session.commit()

    await _wipe()
    yield
    await _wipe()


@pytest.mark.asyncio
async def test_recommend_lab_order_api_creates_draft_unlocked_order(client, auth_headers, _clean_lab_orders):
    now = dt.datetime.now(dt.UTC)
    visit_id = uuid4()
    async with SessionLocal() as session:
        session.add(
            Visit(
                id=visit_id,
                patient_id=patient_id(1),
                doctor_id=None,
                state="TRIAGED",
                triage_session_id=None,
                lab_order_id=None,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()

    resp = await client.post(
        "/api/v1/lab-orders/recommend",
        headers=auth_headers("doctor"),
        json={"visit_id": str(visit_id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert body["locked"] is False
    assert len(body["items"]) >= 3
    sources = {item["source"] for item in body["items"]}
    assert sources & {"rule", "both"}
