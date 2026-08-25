from pydantic import BaseModel


class Citation(BaseModel):
    n: int
    title: str
    source: str
    url: str | None = None
    snippet: str
    published: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict = {}


class ErrorEnvelope(BaseModel):
    error: ErrorDetail
