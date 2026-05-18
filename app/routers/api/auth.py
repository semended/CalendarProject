from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user_api, login_session, logout_session
from app.jwt_auth import encode_access_token
from app.models import User
from app.schemas import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserMe,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserMe)
async def api_login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await auth_service.authenticate(db, payload.email, payload.password)
    except auth_service.InvalidCredentials:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    login_session(request, user)
    await auth_service.record_login(db, user)
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
    try:
        user = await auth_service.register(
            db,
            email=payload.email,
            name=payload.name,
            surname=payload.surname,
            password=payload.password,
            patronymic=payload.patronymic,
        )
    except auth_service.InvalidEmail:
        # На практике сюда не дойдём: RegisterRequest.email — EmailStr,
        # отлуп прилетит 422 ещё до сервиса. Оставлено как явный контракт.
        raise HTTPException(status_code=422, detail="Некорректный адрес почты")
    except auth_service.UserAlreadyExists:
        raise HTTPException(status_code=409, detail="Пользователь с такой почтой уже существует")
    login_session(request, user)
    await auth_service.record_login(db, user)
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
    try:
        user = await auth_service.authenticate(db, form_data.username, form_data.password)
    except auth_service.InvalidCredentials:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    await auth_service.record_login(db, user)
    return TokenResponse(access_token=encode_access_token(user.id))


@router.post("/refresh", response_model=TokenResponse)
async def api_refresh_token(user: User = Depends(get_current_user_api)):
    """Выдаёт свежий JWT по предъявлении валидного существующего.

    `get_current_user_api` принимает и Bearer, и cookie — этого достаточно для
    типичного клиентского флоу (стартовали с /token, периодически рефрешим
    до истечения 7-дневного TTL). Без отдельной refresh-токен таблицы:
    учебная схема не требует, а хранить отдельный токен дольше access'а
    без revoke-инфраструктуры — самообман.
    """
    return TokenResponse(access_token=encode_access_token(user.id))
