from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/files", tags=["files"])


@router.post("")
async def upload_file() -> dict:
    raise not_implemented("file upload owned by pratyaksh")


@router.get("/{file_id}")
async def get_file(file_id: UUID) -> dict:
    raise not_implemented("file fetch owned by pratyaksh")
