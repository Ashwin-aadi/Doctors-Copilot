"""End-to-end patient journey, driven over HTTP.

Walks the seeded demo visit from TRIAGED all the way to PRESCRIBED through the
real API surface: triage conversation, lab order approval, an OCR'd document
landing, the copilot brief, the doctor consulting, and the signed prescription
closing the visit. Only the LLM and the vector retrieval are substituted, for
determinism; Postgres, the visit state machine, the routers and the auth
dependencies are all real.

Requires `scripts/seed.py` to have been run against DATABASE_URL. Skipped when
the database is unreachable, the way the other integration tests are.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

from app.db.models.clinical import LabOrder, LabResult, Prescription, Visit
from app.db.models.document import Document, FileObject
from app.db.session import SessionLocal
from app.main import app
from app.rag import guardrails
from app.rag.store import Hit
from app.schemas.visit import VisitState

PATIENT_1 = UUID("00000000-0000-0000-0000-000000000101")
DOCTOR_1 = UUID("00000000-0000-0000-0000-000000000201")
DOCTOR_USER_1 = UUID("00000000-0000-0000-0000-000000000401")

JOURNEY_VISIT = UUID("00000000-0000-0000-0000-0000000003e2")
JOURNEY_FILE = UUID("00000000-0000-0000-0000-0000000003e3")
JOURNEY_DOCUMENT = UUID("00000000-0000-0000-0000-0000000003e4")


def _hit(title: str, text: str) -> Hit:
    return Hit(
        id=title.lower().replace(" ", "-"),
        text=text,
        score=0.9,
        metadata={
            "title": title,
            "source": "ICMR Standard Treatment Guidelines",
            "url": f"https://www.icmr.gov.in/{title.lower().replace(' ', '-')}",
            "section": "management",
            "doc_type": "guideline",
            "published": "2022",
            "region": "IN",
        },
    )


_HITS = [
    _hit(
        "Type 2 Diabetes Management",
        "Metformin remains first-line therapy for type 2 diabetes in Indian adults. "
        "An HbA1c above 9 percent warrants review of adherence and intensification.",
    ),
    _hit(
        "Glycaemic Monitoring",
        "HbA1c should be repeated every three months until the target is reached.",
    ),
    _hit(
        "Renal Screening in Diabetes",
        "Annual screening for albuminuria and serum creatinine is recommended.",
    ),
]


@pytest_asyncio.fixture(autouse=True)
async def _require_seeded_db():
    try:
        async with SessionLocal() as session:
            found = await session.execute(select(Visit.id).where(Visit.patient_id == PATIENT_1))
            if found.scalars().first() is None:
                pytest.skip("database not seeded; run scripts/seed.py")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable: {exc}")


@pytest_asyncio.fixture(autouse=True)
async def _journey_fixtures():
    """A visit of this test's own, so a re-run is not blocked by the state the
    previous run left the shared demo visit in."""

    async with SessionLocal() as session:
        await _cleanup(session)
        session.add(
            Visit(
                id=JOURNEY_VISIT,
                patient_id=PATIENT_1,
                doctor_id=DOCTOR_1,
                state=VisitState.TRIAGED.value,
                triage_session_id=None,
                lab_order_id=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    yield

    async with SessionLocal() as session:
        await _cleanup(session)
        await session.commit()


async def _cleanup(session) -> None:
    """`visits.lab_order_id` and `lab_orders.visit_id` reference each other, so
    the link has to be broken before either row can go."""

    await session.execute(delete(Prescription).where(Prescription.visit_id == JOURNEY_VISIT))
    await session.execute(delete(LabResult).where(LabResult.document_id == JOURNEY_DOCUMENT))
    await session.execute(delete(Document).where(Document.id == JOURNEY_DOCUMENT))
    await session.execute(delete(FileObject).where(FileObject.id == JOURNEY_FILE))
    await session.execute(
        update(Visit).where(Visit.id == JOURNEY_VISIT).values(lab_order_id=None)
    )
    await session.execute(delete(LabOrder).where(LabOrder.visit_id == JOURNEY_VISIT))
    await session.execute(delete(Visit).where(Visit.id == JOURNEY_VISIT))


@pytest.fixture(autouse=True)
def _deterministic_rag(monkeypatch):
    """Substitute the LLM and retrieval only. Everything else on the path is real."""

    async def _fake_hybrid(collection, query, k=8, where=None):
        return _HITS[:k]

    async def _fake_complete(prompt, *, system=None, max_tokens=1024, temperature=0.2):
        return "How long have you had these symptoms?"

    async def _fake_json_complete(prompt, *, schema, system=None, retries=2):
        from app.schemas.common import Citation

        fields = schema.model_fields
        payload: dict = {}
        if "severity_esi" in fields:
            payload.update(
                severity_esi=3,
                specialty="general_medicine",
                rationale="Uncontrolled type 2 diabetes needs review [1].",
                suggested_labs=[
                    {"name": "HbA1c", "reason": "assess glycaemic control", "source": "rag"},
                    {"name": "Serum creatinine", "reason": "renal screening", "source": "rag"},
                ],
            )
        if "summary" in fields:
            payload.update(
                summary="Uncontrolled type 2 diabetes on metformin, HbA1c 9.2 percent [1].",
                differentials=["uncontrolled type 2 diabetes", "secondary hyperglycaemia"],
                recommended_procedures=["repeat HbA1c in three months"],
                cautions=["penicillin allergy recorded"],
            )
        payload["citations"] = [
            Citation(
                n=i + 1,
                title=h.metadata["title"],
                source=h.metadata["source"],
                url=h.metadata["url"],
                snippet=h.text[:200],
                published="2022",
            )
            for i, h in enumerate(_HITS)
        ]
        payload["confidence"] = 0.8
        return schema(**{k: v for k, v in payload.items() if k in fields})

    for module in ("app.rag.triage_rag", "app.rag.clinical_rag"):
        monkeypatch.setattr(f"{module}.hybrid", _fake_hybrid, raising=False)
        monkeypatch.setattr(f"{module}.json_complete", _fake_json_complete, raising=False)
    monkeypatch.setattr("app.rag.triage_rag.complete", _fake_complete)

    # Skip the cross-encoder download; keep guardrail behaviour deterministic.
    monkeypatch.setattr(guardrails, "_score_sentences", lambda text, hits: None)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=60.0) as ac:
        yield ac


@pytest.fixture
def doctor_headers():
    from app.core.security import create_access_token

    return {"Authorization": f"Bearer {create_access_token(DOCTOR_USER_1, 'doctor')}"}


async def _advance(client, headers, target: VisitState):
    return await client.post(
        f"/api/v1/visits/{JOURNEY_VISIT}/advance",
        headers=headers,
        json={"target": target.value},
    )


@pytest.mark.asyncio
async def test_journey_walks_triaged_to_prescribed(client, doctor_headers):
    # --- 1. Triage conversation over HTTP -----------------------------------
    started = await client.post("/api/v1/triage/session", json={})
    assert started.status_code == 200, started.text
    session_id = started.json()["session_id"]

    # Answer until the interview closes itself -- the assistant asks at most
    # eight questions, then finalises.
    answers = [
        "my sugar has been high for two months and I feel very tired",
        "it started about two months ago",
        "I take metformin twice a day",
        "no fever, no vomiting, no chest pain",
        "I get tired climbing stairs",
        "my last HbA1c was around nine",
        "no other complaints",
        "nothing else to add",
    ]
    for answer in answers:
        turn = await client.post(
            f"/api/v1/triage/{session_id}/message",
            json={"session_id": session_id, "content": answer},
        )
        assert turn.status_code == 200, turn.text
        if turn.json()["done"]:
            break
    assert turn.json()["done"], "triage must finalise within eight questions"

    result = await client.get(f"/api/v1/triage/{session_id}/result")
    assert result.status_code == 200, result.text
    assert result.json()["triage_colour"] in ("red", "yellow", "green")

    # --- 2. Triage attaches to the visit; TRIAGED -> LABS_SUGGESTED ----------
    async with SessionLocal() as session:
        visit = await session.get(Visit, JOURNEY_VISIT)
        visit.triage_session_id = UUID(session_id)
        await session.commit()

    response = await _advance(client, doctor_headers, VisitState.LABS_SUGGESTED)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == VisitState.LABS_SUGGESTED.value

    # --- 3. Doctor signs the lab order; LABS_SUGGESTED -> LABS_APPROVED ------
    order_id = uuid4()
    async with SessionLocal() as session:
        session.add(
            LabOrder(
                id=order_id,
                visit_id=JOURNEY_VISIT,
                patient_id=PATIENT_1,
                items=[{"name": "HbA1c"}, {"name": "Serum creatinine"}],
                status="approved",
                approved_by=DOCTOR_USER_1,
                approved_at=datetime.now(UTC),
                content_hash="e2e",
                locked=True,
            )
        )
        visit = await session.get(Visit, JOURNEY_VISIT)
        visit.lab_order_id = order_id
        await session.commit()

    # The state machine refuses to skip ahead, whichever step is skipped.
    skipped = await _advance(client, doctor_headers, VisitState.BRIEF_READY)
    assert skipped.status_code == 409
    assert skipped.json()["error"]["code"] == "CONFLICT"

    response = await _advance(client, doctor_headers, VisitState.LABS_APPROVED)
    assert response.status_code == 200, response.text

    # --- 4. Lab report OCR'd; LABS_APPROVED -> RESULTS_UPLOADED -------------
    async with SessionLocal() as session:
        session.add(
            FileObject(
                id=JOURNEY_FILE,
                patient_id=PATIENT_1,
                sha256="e2e" + "0" * 61,
                path="/tmp/e2e-lab-report.pdf",
                mime="application/pdf",
                size=1024,
                uploaded_by=DOCTOR_USER_1,
            )
        )
        await session.flush()
        session.add(
            Document(
                id=JOURNEY_DOCUMENT,
                patient_id=PATIENT_1,
                file_id=JOURNEY_FILE,
                status="done",
                engine="tesseract",
                mean_confidence=0.91,
                text="HbA1c 9.2 % (ref 4.0-5.6)",
            )
        )
        await session.flush()
        session.add(
            LabResult(
                document_id=JOURNEY_DOCUMENT,
                patient_id=PATIENT_1,
                test_name="HbA1c",
                normalized_name="hemoglobin_a1c",
                value_num=9.2,
                unit="%",
                ref_low=4.0,
                ref_high=5.6,
                flag="high",
                confidence=0.91,
                observed_at=datetime.now(UTC),
            )
        )
        await session.commit()

    response = await _advance(client, doctor_headers, VisitState.RESULTS_UPLOADED)
    assert response.status_code == 200, response.text
    body = response.json()
    assert any(doc["id"] == str(JOURNEY_DOCUMENT) for doc in body["documents"])

    # --- 5. Copilot brief; RESULTS_UPLOADED -> BRIEF_READY ------------------
    brief = await client.post(
        "/api/v1/copilot/brief", headers=doctor_headers, json={"visit_id": str(JOURNEY_VISIT)}
    )
    assert brief.status_code == 200, brief.text
    assert brief.json()["citations"], "brief must be grounded in retrieved sources"

    response = await _advance(client, doctor_headers, VisitState.BRIEF_READY)
    assert response.status_code == 200, response.text
    assert response.json()["brief"] is not None

    # --- 6. Consultation; BRIEF_READY -> CONSULTED --------------------------
    response = await _advance(client, doctor_headers, VisitState.CONSULTED)
    assert response.status_code == 200, response.text

    # A prescription must exist and be signed before the visit can close.
    premature = await _advance(client, doctor_headers, VisitState.PRESCRIBED)
    assert premature.status_code == 409
    assert "prescription" in premature.json()["error"]["message"]

    # --- 7. Signed prescription; CONSULTED -> PRESCRIBED --------------------
    async with SessionLocal() as session:
        session.add(
            Prescription(
                visit_id=JOURNEY_VISIT,
                patient_id=PATIENT_1,
                items=[{"name": "metformin", "ingredient": "metformin", "dose": "1000mg BD"}],
                approved_by=DOCTOR_USER_1,
                approved_at=datetime.now(UTC),
                content_hash="e2e-rx",
                locked=True,
            )
        )
        await session.commit()

    response = await _advance(client, doctor_headers, VisitState.PRESCRIBED)
    assert response.status_code == 200, response.text
    assert response.json()["state"] == VisitState.PRESCRIBED.value

    # --- 8. The assembled visit carries every top-level key -----------------
    final = await client.get(f"/api/v1/visits/{JOURNEY_VISIT}", headers=doctor_headers)
    assert final.status_code == 200, final.text
    payload = final.json()

    for key in ("id", "patient_id", "doctor_id", "state", "triage", "documents", "updated_at"):
        assert payload[key] is not None, f"{key} missing from the assembled visit"
    assert payload["state"] == VisitState.PRESCRIBED.value
    assert payload["triage"]["triage_colour"] in ("red", "yellow", "green")
    assert payload["lab_order_id"] is not None


@pytest.mark.asyncio
async def test_visit_routes_reject_anonymous_callers(client):
    read = await client.get(f"/api/v1/visits/{JOURNEY_VISIT}")
    assert read.status_code == 401
    assert read.json()["error"]["code"].startswith("AUTH")

    advance = await client.post(f"/api/v1/visits/{JOURNEY_VISIT}/advance", json={})
    assert advance.status_code == 401


@pytest.mark.asyncio
async def test_websocket_requires_a_token():
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    with TestClient(app) as test_client, pytest.raises(WebSocketDisconnect) as excinfo:
        with test_client.websocket_connect(f"/ws/visit/{JOURNEY_VISIT}") as ws:
            ws.receive_text()

    assert excinfo.value.code == 1008
