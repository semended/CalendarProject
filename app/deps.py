from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.jwt_auth import decode_access_token
from app.models import User

# tokenUrl указывает Swagger UI на endpoint для получения токена.
# auto_error=False — если заголовка Authorization нет, получаем None и
# падаем обратно на cookie-сессии (Jinja-пользователи API тоже работает).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


class RedirectToLogin(Exception):
    pass


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    user = await crud.get_user_by_id(db, int(user_id))
    if user is None:
        request.session.pop("user_id", None)
    return user


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_current_user_optional(request, db)
    if user is None:
        raise RedirectToLogin()
    return user


async def get_current_user_api(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Двойная авторизация для /api/v1/*: Authorization: Bearer … имеет приоритет,
    иначе падаем на cookie-сессию (чтобы Swagger UI и Jinja-юзеры работали одинаково)."""
    if token is not None:
        user_id = decode_access_token(token)
        if user_id is None:
            raise HTTPException(status_code=401, detail="Невалидный токен")
        user = await crud.get_user_by_id(db, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Пользователь не найден")
        return user
    user = await get_current_user_optional(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return user


def login_session(request: Request, user: User) -> None:
    request.session["user_id"] = user.id


def logout_session(request: Request) -> None:
    request.session.pop("user_id", None)
