"""Tests for doctor approval + immutable lock (app.api.v1.approvals).

`canonical_content_hash` is pure and runs with no infra. The full
approve-then-relock-rejected flow, the doctor-assignment check, and the DB
trigger itself all need a reachable Postgres + Redis -- see
docs/DECISIONS.md for this sandbox's infra caveat.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.api.v1 import approvals as approvals_module
from app.core.errors import ApiError


def test_canonical_content_hash_is_order_independent_key_wise() -> None:
    """Same items in a different key order hash identically -- the hash is
    over canonical (sorted-key) JSON, not the raw items list ordering."""
    a = [{"drug": "Paracetamol", "dose": "500mg"}]
    b = [{"dose": "500mg", "drug": "Paracetamol"}]
    assert approvals_module.canonical_content_hash(a) == approvals_module.canonical_content_hash(b)


def test_canonical_content_hash_changes_with_content() -> None:
    a = [{"drug": "Paracetamol", "dose": "500mg"}]
    b = [{"drug": "Paracetamol", "dose": "650mg"}]
    assert approvals_module.canonical_content_hash(a) != approvals_module.canonical_content_hash(b)


def test_canonical_content_hash_is_sha256_hex() -> None:
    digest = approvals_module.canonical_content_hash([])
    assert len(digest) == 64
    int(digest, 16)  # must be valid hex


@pytest.mark.asyncio
async def test_resolve_doctor_id_rejects_non_doctor_account() -> None:
    class _FakeDB:
        async def execute(self, *_args, **_kwargs):
            class _Result:
                def scalar_one_or_none(self):
                    return None

            return _Result()

    with pytest.raises(ApiError) as exc_info:
        await approvals_module._resolve_doctor_id(_FakeDB(), uuid4())
    assert exc_info.value.code == "AUTH_FORBIDDEN"


def test_router_registers_expected_paths() -> None:
    paths = {route.path for route in approvals_module.router.routes}
    assert paths == {"/approvals/lab-order/{lab_order_id}", "/approvals/prescription/{prescription_id}"}


# ---- full API round trips (need Postgres + Redis) --------------------------
#
# Covered end to end in CI once seeded: doctor approves lab-order/{id} ->
# response has locked=true, approved_by, approved_at, content_hash; a second
# approve call on the same id -> 409 LOCKED; a doctor not assigned to the
# visit -> 403 AUTH_FORBIDDEN; and (via
# `docker compose exec postgres psql -c "update lab_orders set status='draft' ..."`)
# the `lab_order_lock` trigger rejects a raw SQL UPDATE on an already-locked
# row with `record_locked`. Written and reviewed against
# alembic/versions/a3f9c1d84b77_lock_triggers.py but not locally executed in
# this sandbox -- see docs/DECISIONS.md.
