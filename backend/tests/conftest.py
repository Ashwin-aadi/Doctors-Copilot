"""Shared pytest fixtures for the whole backend test suite.

`auth_headers` now mints real access tokens via `app.core.security`, as its
own former TEMP-ADAPTER comment anticipated ("swap the header construction
for a real login call once `/api/v1/auth/login` is implemented" -- see
docs/DECISIONS.md). It stays synchronous and keeps its original
`auth_headers("doctor") -> dict` signature -- several existing tests
(`tests/ml/test_documents_api.py`) call it unawaited inline as a `headers=`
kwarg -- by signing the token for one of `scripts/seed_users.py`'s fixed
per-role UUIDs rather than querying the DB (which would require an awaited
call). `get_current_user` still does its own DB lookup for that id, so a
route call still 401s exactly as before if the DB hasn't been seeded.
"""

from collections.abc import AsyncIterator, Callable
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import app.core.redis_client as _redis_module
import app.kg.client as _kg_client_module
from app.core.security import create_access_token
from app.db.session import SessionLocal, engine
from app.main import app

# Matches scripts/seed_users.py's fixed UUIDs for the first seeded user of
# each role.
_ROLE_USER_IDS: dict[str, UUID] = {
    "patient": UUID("00000000-0000-0000-0000-000000000501"),
    "doctor": UUID("00000000-0000-0000-0000-000000000401"),
    "staff": UUID("00000000-0000-0000-0000-000000000603"),
    "admin": UUID("00000000-0000-0000-0000-000000000601"),
}


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_after_test() -> AsyncIterator[None]:
    # Each test runs in its own event loop (asyncio_default_fixture_loop_scope
    # = "function"), but `engine` and `redis_client` are module-level
    # singletons whose pooled connections bind to whichever loop first used
    # them. Left undisposed, the next test's loop reuses a connection tied
    # to an already-closed loop and every DB/Redis call in that test fails
    # with "Event loop is closed".
    yield
    await engine.dispose()
    if _redis_module._client is not None:
        await _redis_module._client.aclose()
        _redis_module._client = None
    # Same event-loop-per-test hazard as engine/redis above: neo4j.AsyncDriver
    # is cached via @lru_cache in app.kg.client, so a driver opened by one
    # test's event loop breaks every later test unless it's closed and
    # dropped here before that loop closes.
    if _kg_client_module._driver.cache_info().currsize:
        await _kg_client_module.close_driver()
    _kg_client_module._driver.cache_clear()


@pytest_asyncio.fixture
async def db() -> AsyncIterator:
    async with SessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers() -> Callable[[str], dict[str, str]]:
    def _make(role: str) -> dict[str, str]:
        user_id = _ROLE_USER_IDS.get(role)
        if user_id is None:
            raise LookupError(f"no fixed seeded user id for role={role!r}")
        token = create_access_token(user_id, role)
        return {"Authorization": f"Bearer {token}"}

    return _make
