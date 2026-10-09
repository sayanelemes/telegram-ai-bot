from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.api.deps import get_current_user, get_user_repo
from app.api.schemas import UserResponse
from app.api.auth import verify_login_code, create_auth_token
from app.database.models import UserDB
from app.database.repositories.user_repository import UserRepository
from app.config.settings import settings

router = APIRouter(tags=["auth"])


class VerifyCodeRequest(BaseModel):
    code: str


class VerifyCodeResponse(BaseModel):
    success: bool
    token: str
    user: UserResponse


class TokenResponse(BaseModel):
    token: str


@router.get("/health")
async def health_check():
    return {"status": "ok", "app": "nutritracker"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: UserDB = Depends(get_current_user)):
    return UserResponse(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        timezone=user.timezone,
    )


@router.post("/auth/code", response_model=VerifyCodeResponse)
async def login_with_code(
    payload: VerifyCodeRequest,
    user_repo: UserRepository = Depends(get_user_repo),
):
    tg_id = verify_login_code(payload.code)
    if not tg_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный или истёкший код. Запросите новый код в Telegram-боте командой /code или /login.",
        )

    user = await user_repo.get_by_telegram_id(tg_id)
    if not user:
        user = await user_repo.get_or_create_user(
            telegram_id=tg_id,
            username=None,
            first_name="Пользователь",
            timezone=settings.DEFAULT_TIMEZONE,
        )

    token = create_auth_token(tg_id)
    return VerifyCodeResponse(
        success=True,
        token=token,
        user=UserResponse(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
            timezone=user.timezone,
        ),
    )


@router.get("/auth/token", response_model=TokenResponse)
async def get_my_standalone_token(user: UserDB = Depends(get_current_user)):
    token = create_auth_token(user.telegram_id)
    return TokenResponse(token=token)
