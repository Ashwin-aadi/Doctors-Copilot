from fastapi import APIRouter

from app.core.errors import not_implemented
from app.schemas.ml import InteractionReport, MedCandidate, SoapSummary

router = APIRouter(prefix="/ml", tags=["ml"])


@router.post("/entities")
async def extract_entities() -> dict:
    raise not_implemented("entity extraction owned by virat")


@router.post("/interactions", response_model=InteractionReport)
async def check_interactions() -> InteractionReport:
    raise not_implemented("interaction checking owned by virat")


@router.post("/labs/flag")
async def flag_labs() -> list:
    raise not_implemented("lab flagging owned by virat")


@router.post("/summary", response_model=SoapSummary)
async def summarize() -> SoapSummary:
    raise not_implemented("SOAP summary owned by virat")


@router.post("/medications/suggest", response_model=list[MedCandidate])
async def suggest_medications() -> list[MedCandidate]:
    raise not_implemented("medication suggestion owned by virat")
