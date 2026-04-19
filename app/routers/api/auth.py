from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.deps import get_current_user_api, login_session, logout_session
from app.email import send_verification_email
from app.jwt_auth import encode_access_token
from app.models import User
from app.schemas import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserMe,
)
from app.security import hash_password, is_hashed, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserMe)
async def api_login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await crud.get_user_by_email(db, payload.email)
    if user is None or not verify_password(payload.password, user.password):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if not is_hashed(user.password):
        await crud.update_user_password(db, user.id, hash_password(payload.password))
    login_session(request, user)
    return user


@router.post("/logout", response_model=MessageResponse)
async def api_logout(
    request: Request,
    _: User = Depends(get_current_user_api),
):
    logout_session(request)
    return MessageResponse(message="Выход выполнен")


@router.post("/register", response_model=UserMe, status_code=201)
async def api_register(
    request: Request,
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    if await crud.get_user_by_email(db, payload.email) is not None:
        raise HTTPException(status_code=409, detail="Пользователь с такой почтой уже существует")
    user = await crud.add_user(
        db,
        email=payload.email,
        name=payload.name,
        surname=payload.surname,
        password=hash_password(payload.password),
        patronymic=payload.patronymic,
    )
    send_verification_email(user.email, user.name)
    login_session(request, user)
    return user


@router.get("/me", response_model=UserMe)
async def api_me(user: User = Depends(get_current_user_api)):
    return user


@router.post("/token", response_model=TokenResponse)
async def api_issue_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """OAuth2 password grant: form-data с username (email) и password → JWT.

    Отдельно от /login: /login ставит cookie-сессию (для Jinja / браузера),
    а /token выдаёт stateless Bearer-токен (для мобилок / внешних клиентов)."""
    user = await crud.get_user_by_email(db, form_data.username)
    if user is None or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if not is_hashed(user.password):
        await crud.update_user_password(db, user.id, hash_password(form_data.password))
    return TokenResponse(access_token=encode_access_token(user.id))
