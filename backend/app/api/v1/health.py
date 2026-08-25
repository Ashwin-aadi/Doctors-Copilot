from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "db": "ok",
        "redis": "ok",
        "neo4j": "ok",
        "chroma": "ok",
        "llm": "ok",
    }
