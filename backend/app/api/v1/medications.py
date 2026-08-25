from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/medications", tags=["medications"])


@router.get("/generic")
async def generic_lookup(brand: str | None = None) -> dict:
    raise not_implemented("brand-to-generic mapping owned by niyati")
