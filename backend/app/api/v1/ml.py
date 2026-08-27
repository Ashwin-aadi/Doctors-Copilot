from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, get_current_user
from app.db.session import get_db
from app.ml.lab_flags import flag_labs as _flag_labs
from app.ml.med_suggest import suggest_medications as _suggest_medications
from app.ml.ner import extract as _extract_entities
from app.ml.safety import check_interactions as _check_interactions
from app.ml.schemas_ml import (
    EntityBundle,
    EntityRequest,
    InteractionRequest,
    LabFlagRequest,
    LabResultExtended,
    MedSuggestRequest,
    SummaryRequest,
)
from app.ml.summary import build_summary as _build_summary
from app.schemas.ml import InteractionReport, MedCandidate, SoapSummary

router = APIRouter(prefix="/ml", tags=["ml"])


@router.post("/entities", response_model=EntityBundle)
async def extract_entities(
    req: EntityRequest, current_user: CurrentUser = Depends(get_current_user)
) -> EntityBundle:
    return await _extract_entities(req.text)


@router.post("/interactions", response_model=InteractionReport)
async def check_interactions(
    req: InteractionRequest, current_user: CurrentUser = Depends(get_current_user)
) -> InteractionReport:
    return await _check_interactions(req)


@router.post("/labs/flag", response_model=list[LabResultExtended])
async def flag_labs(
    req: LabFlagRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[LabResultExtended]:
    return await _flag_labs(db, req.patient_id, req.results)


@router.post("/summary", response_model=SoapSummary)
async def summarize(
    req: SummaryRequest, current_user: CurrentUser = Depends(get_current_user)
) -> SoapSummary:
    return await _build_summary(req)


@router.post("/medications/suggest", response_model=list[MedCandidate])
async def suggest_medications(
    req: MedSuggestRequest, current_user: CurrentUser = Depends(get_current_user)
) -> list[MedCandidate]:
    return await _suggest_medications(req)
