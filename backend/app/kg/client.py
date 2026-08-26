"""Neo4j driver singleton. Every KG call goes through `run_query`, which
never raises to its caller -- an unreachable graph degrades to an empty
result rather than failing a visit, triage, or brief request.
"""

from functools import lru_cache
from typing import Any

from neo4j import AsyncGraphDatabase

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
settings = get_settings()


@lru_cache
def _driver():
    return AsyncGraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )


async def run_query(cypher: str, **params: Any) -> list[dict]:
    try:
        driver = _driver()
        async with driver.session() as session:
            result = await session.run(cypher, **params)
            return [dict(record) async for record in result]
    except Exception as exc:  # noqa: BLE001
        log.warning("kg_unavailable", error=str(exc))
        return []


async def run_write(cypher: str, **params: Any) -> None:
    try:
        driver = _driver()
        async with driver.session() as session:
            await session.run(cypher, **params)
    except Exception as exc:  # noqa: BLE001
        log.warning("kg_write_failed", error=str(exc))


async def close_driver() -> None:
    try:
        await _driver().close()
    except Exception:  # noqa: BLE001
        pass
