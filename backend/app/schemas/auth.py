from uuid import UUID

from pydantic import BaseModel


class RegisterIn(BaseModel):
    email: str
    password: str
    role: str
    captcha_token: str


class LoginIn(BaseModel):
    email: str
    password: str
    captcha_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    email: str
    role: str
    is_active: bool
