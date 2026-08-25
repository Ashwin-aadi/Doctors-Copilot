from fastapi import APIRouter

from app.core.errors import not_implemented
from app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenOut)
async def register(body: RegisterIn) -> TokenOut:
    raise not_implemented("auth register owned by pratyaksh")


@router.post("/auth/login", response_model=TokenOut)
async def login(body: LoginIn) -> TokenOut:
    raise not_implemented("auth login owned by pratyaksh")


@router.post("/auth/refresh", response_model=TokenOut)
async def refresh() -> TokenOut:
    raise not_implemented("auth refresh owned by pratyaksh")


@router.post("/auth/logout")
async def logout() -> dict:
    raise not_implemented("auth logout owned by pratyaksh")


@router.get("/auth/me", response_model=UserOut)
async def me() -> UserOut:
    raise not_implemented("auth me owned by pratyaksh")


@router.get("/captcha/challenge")
async def captcha_challenge() -> dict:
    raise not_implemented("captcha challenge owned by pratyaksh")


@router.post("/captcha/verify")
async def captcha_verify() -> dict:
    raise not_implemented("captcha verify owned by pratyaksh")
