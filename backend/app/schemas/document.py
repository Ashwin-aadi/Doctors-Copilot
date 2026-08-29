from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class LabResultOut(BaseModel):
    test_name: str
    normalized_name: str
    value: float | str
    unit: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    flag: Literal["critical", "high", "low", "normal", "unknown"] = "unknown"
    confidence: float
    page: int = 1
    bbox: list[float] | None = None


class DocumentOut(BaseModel):
    id: UUID
    patient_id: UUID
    file_id: UUID
    status: Literal["queued", "processing", "done", "failed"]
    engine: str | None = None
    mean_confidence: float | None = None
    text: str | None = None
    labs: list[LabResultOut] = []
    error: str | None = None
    test_name: str | None = None
