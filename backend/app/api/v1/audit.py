from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
async def list_audit() -> list:
    raise not_implemented("audit log owned by pratyaksh")
