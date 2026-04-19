from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.deps import get_current_user_api, login_session, logout_session
from app.models import User
from app.schemas import LoginRequest, MessageResponse, RegisterRequest, UserMe
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
    login_session(request, user)
    return user


@router.get("/me", response_model=UserMe)
async def api_me(user: User = Depends(get_current_user_api)):
    return user
