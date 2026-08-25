from fastapi import APIRouter

from app.core.errors import not_implemented

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/patient")
async def patient_chat() -> None:
    raise not_implemented("patient chatbot lands in A3.2")
