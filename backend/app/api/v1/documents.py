from uuid import UUID

from fastapi import APIRouter

from app.core.errors import not_implemented
from app.schemas.document import DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentOut)
async def upload_document() -> DocumentOut:
    raise not_implemented("document upload owned by virat")


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: UUID) -> DocumentOut:
    raise not_implemented("document fetch owned by virat")
