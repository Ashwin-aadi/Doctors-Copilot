"""Visit state machine tests.

The transition table and its guards are pure logic, so these run against a
fake session with no Postgres, Redis, Neo4j or Chroma behind them. Six legal
transitions are walked end to end; illegal ones -- skipping a step, going
backwards, moving past the terminal state, and moving forward without the
database precondition -- must all come back as 409 CONFLICT.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.errors import ApiError
from app.db.models.clinical import LabOrder, Prescription, Visit
from app.schemas.visit import VisitState
from app.services import visit as visit_service

LEGAL_PATH = [
    (VisitState.TRIAGED, VisitState.LABS_SUGGESTED),
    (VisitState.LABS_SUGGESTED, VisitState.LABS_APPROVED),
    (VisitState.LABS_APPROVED, VisitState.RESULTS_UPLOADED),
    (VisitState.RESULTS_UPLOADED, VisitState.BRIEF_READY),
    (VisitState.BRIEF_READY, VisitState.CONSULTED),
    (VisitState.CONSULTED, VisitState.PRESCRIBED),
]

ILLEGAL_PAIRS = [
    (VisitState.TRIAGED, VisitState.BRIEF_READY),        # skips two steps
    (VisitState.LABS_APPROVED, VisitState.TRIAGED),      # backwards
    (VisitState.BRIEF_READY, VisitState.LABS_APPROVED),  # backwards
    (VisitState.TRIAGED, VisitState.PRESCRIBED),         # skips the whole flow
    (VisitState.RESULTS_UPLOADED, VisitState.CONSULTED),  # skips the brief
]


def _visit(state: VisitState, *, lab_order_id=None) -> Visit:
    return Visit(
        id=uuid4(),
        patient_id=uuid4(),
        doctor_id=uuid4(),
        state=state.value,
        triage_session_id=None,
        lab_order_id=lab_order_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class _FakeDb:
    """Minimal AsyncSession stand-in: `get` serves the visit and whatever
    guard object the test wants found, `execute` decides whether the
    document/prescription precondition query returns a row."""

    def __init__(self, visit: Visit, *, guard_object=None, row_found: bool = True):
        self.visit = visit
        self.guard_object = guard_object
        self.row_found = row_found

    async def get(self, model, id_):
        if model is Visit:
            return self.visit if id_ == self.visit.id else None
        if self.guard_object is not None and isinstance(self.guard_object, model):
            return self.guard_object
        return None

    async def execute(self, _stmt):
        found = self.row_found
        row = uuid4() if found else None

        class _R:
            def scalar_one_or_none(self):
                return row

        return _R()

    async def commit(self):
        return None

    async def refresh(self, _obj):
        return None


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch):
    """A transition publishes to Redis and re-syncs the KG and the patient
    chat corpus. None of that is under test here."""

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(visit_service, "publish", _noop)
    monkeypatch.setattr("app.kg.ingest.sync_patient", _noop)
    monkeypatch.setattr("app.rag.ingest_patient.sync_patient", _noop)


def _db_for(from_state: VisitState, to_state: VisitState) -> _FakeDb:
    """Build a session whose database preconditions are satisfied for the
    transition under test."""

    if to_state is VisitState.LABS_APPROVED:
        order = LabOrder(id=uuid4(), visit_id=uuid4(), patient_id=uuid4(), items=[], locked=True)
        visit = _visit(from_state, lab_order_id=order.id)
        return _FakeDb(visit, guard_object=order)
    if to_state is VisitState.PRESCRIBED:
        signed = Prescription(id=uuid4(), visit_id=uuid4(), patient_id=uuid4(), items=[], locked=True)
        return _FakeDb(_visit(from_state), guard_object=signed, row_found=True)
    return _FakeDb(_visit(from_state))


# ------------------------------------------------------------ legal moves


@pytest.mark.parametrize(("from_state", "to_state"), LEGAL_PATH)
@pytest.mark.asyncio
async def test_legal_transition_is_accepted(from_state, to_state):
    db = _db_for(from_state, to_state)
    updated = await visit_service.advance(db, db.visit.id, to_state)
    assert updated.state == to_state.value


@pytest.mark.asyncio
async def test_advance_without_target_takes_the_next_step():
    db = _FakeDb(_visit(VisitState.TRIAGED))
    updated = await visit_service.advance(db, db.visit.id)
    assert updated.state == VisitState.LABS_SUGGESTED.value


@pytest.mark.asyncio
async def test_full_path_walks_triaged_to_prescribed():
    state = VisitState.TRIAGED
    for from_state, to_state in LEGAL_PATH:
        assert state is from_state
        db = _db_for(from_state, to_state)
        updated = await visit_service.advance(db, db.visit.id, to_state)
        state = VisitState(updated.state)
    assert state is VisitState.PRESCRIBED


# ---------------------------------------------------------- illegal moves


@pytest.mark.parametrize(("from_state", "to_state"), ILLEGAL_PAIRS)
@pytest.mark.asyncio
async def test_illegal_transition_is_rejected(from_state, to_state):
    db = _FakeDb(_visit(from_state))
    with pytest.raises(ApiError) as excinfo:
        await visit_service.advance(db, db.visit.id, to_state)

    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "CONFLICT"


@pytest.mark.asyncio
async def test_advancing_past_the_terminal_state_is_rejected():
    db = _FakeDb(_visit(VisitState.PRESCRIBED))
    with pytest.raises(ApiError) as excinfo:
        await visit_service.advance(db, db.visit.id)

    assert excinfo.value.status_code == 409
    assert "final state" in excinfo.value.message


@pytest.mark.asyncio
async def test_unknown_visit_is_not_found():
    db = _FakeDb(_visit(VisitState.TRIAGED))
    with pytest.raises(ApiError) as excinfo:
        await visit_service.advance(db, uuid4())

    assert excinfo.value.status_code == 404


# --------------------------------------------------------- guard failures


@pytest.mark.asyncio
async def test_labs_approved_requires_a_locked_lab_order():
    order = LabOrder(id=uuid4(), visit_id=uuid4(), patient_id=uuid4(), items=[], locked=False)
    visit = _visit(VisitState.LABS_SUGGESTED, lab_order_id=order.id)
    db = _FakeDb(visit, guard_object=order)

    with pytest.raises(ApiError) as excinfo:
        await visit_service.advance(db, visit.id, VisitState.LABS_APPROVED)

    assert excinfo.value.status_code == 409
    assert "locked" in excinfo.value.message


@pytest.mark.asyncio
async def test_results_uploaded_requires_a_completed_document():
    db = _FakeDb(_visit(VisitState.LABS_APPROVED), row_found=False)

    with pytest.raises(ApiError) as excinfo:
        await visit_service.advance(db, db.visit.id, VisitState.RESULTS_UPLOADED)

    assert excinfo.value.status_code == 409
    assert "document" in excinfo.value.message


@pytest.mark.asyncio
async def test_prescribed_requires_a_signed_prescription():
    db = _FakeDb(_visit(VisitState.CONSULTED), row_found=False)

    with pytest.raises(ApiError) as excinfo:
        await visit_service.advance(db, db.visit.id, VisitState.PRESCRIBED)

    assert excinfo.value.status_code == 409
    assert "prescription" in excinfo.value.message


@pytest.mark.asyncio
async def test_force_guard_bypasses_only_the_precondition_not_the_table():
    """Internal callers that just created the lab order in the same
    transaction skip the guard -- but still cannot jump the state table."""

    db = _FakeDb(_visit(VisitState.LABS_SUGGESTED))
    updated = await visit_service.advance(
        db, db.visit.id, VisitState.LABS_APPROVED, force_guard=True
    )
    assert updated.state == VisitState.LABS_APPROVED.value

    db2 = _FakeDb(_visit(VisitState.TRIAGED))
    with pytest.raises(ApiError):
        await visit_service.advance(
            db2, db2.visit.id, VisitState.PRESCRIBED, force_guard=True
        )


# ------------------------------------------------------------ transition map


def test_transition_table_is_a_single_linear_chain():
    assert visit_service.next_state(VisitState.PRESCRIBED) is None
    for from_state, to_state in LEGAL_PATH:
        assert visit_service.next_state(from_state) is to_state
        assert visit_service.can_advance(from_state, to_state)


@pytest.mark.asyncio
async def test_transition_publishes_visit_updated(monkeypatch):
    published: list[tuple[str, dict]] = []

    async def _capture(channel, payload):
        published.append((channel, payload))

    monkeypatch.setattr(visit_service, "publish", _capture)

    db = _FakeDb(_visit(VisitState.TRIAGED))
    await visit_service.advance(db, db.visit.id)

    assert published, "transition must publish visit.updated"
    channel, payload = published[0]
    assert channel == visit_service.VISIT_CHANNEL
    assert payload["state"] == VisitState.LABS_SUGGESTED.value
    assert payload["from"] == VisitState.TRIAGED.value
    assert payload["visit_id"] == str(db.visit.id)


# ------------------------------------------------------------ moving back


@pytest.mark.asyncio
async def test_rewind_moves_the_visit_to_an_earlier_stage():
    """A brief built before the last report landed has to be reworkable."""
    db = _FakeDb(_visit(VisitState.CONSULTED))
    updated = await visit_service.rewind(db, db.visit.id, VisitState.BRIEF_READY)
    assert updated.state == VisitState.BRIEF_READY.value


@pytest.mark.asyncio
async def test_rewind_skips_straight_back_to_any_earlier_stage():
    db = _FakeDb(_visit(VisitState.CONSULTED))
    updated = await visit_service.rewind(db, db.visit.id, VisitState.LABS_SUGGESTED)
    assert updated.state == VisitState.LABS_SUGGESTED.value


@pytest.mark.asyncio
async def test_rewind_refuses_to_move_forward():
    """Rewind must never become a way around the guards that protect a
    forward transition -- skipping to PRESCRIBED without a signed
    prescription is exactly what `advance` exists to prevent."""
    db = _FakeDb(_visit(VisitState.TRIAGED))
    with pytest.raises(ApiError) as exc:
        await visit_service.rewind(db, db.visit.id, VisitState.PRESCRIBED)
    assert exc.value.code == "CONFLICT"
    assert db.visit.state == VisitState.TRIAGED.value


@pytest.mark.asyncio
async def test_rewind_to_the_current_state_is_a_no_op():
    db = _FakeDb(_visit(VisitState.BRIEF_READY))
    updated = await visit_service.rewind(db, db.visit.id, VisitState.BRIEF_READY)
    assert updated.state == VisitState.BRIEF_READY.value


@pytest.mark.asyncio
async def test_rewind_leaves_a_signed_lab_order_locked():
    """Moving back reworks the stage, never the signature on it."""
    order = LabOrder(id=uuid4(), visit_id=uuid4(), patient_id=uuid4(), items=[], locked=True)
    visit = _visit(VisitState.RESULTS_UPLOADED, lab_order_id=order.id)
    db = _FakeDb(visit, guard_object=order)

    await visit_service.rewind(db, visit.id, VisitState.LABS_SUGGESTED)

    assert order.locked is True
