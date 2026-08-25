"""Shared pytest fixtures for the whole backend test suite.

`client` and `db` are ready to use today. `auth_headers` is a TEMP-ADAPTER:
real JWT issuance lands with Pratyaksh's `app/core/security.py` (CP2). Until
then it returns a role-tagged placeholder header so tests can be written
against the shape of the dependency without blocking on it; swap the header
construction for a real login call once `/api/v1/auth/login` is implemented.
"""

from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.session import SessionLocal
from app.main import app


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
    # TEMP-ADAPTER: remove when Pratyaksh ships app/core/security.py + /auth/login.
    def _make(role: str) -> dict[str, str]:
        return {"Authorization": f"Bearer test-{role}-token"}

    return _make
