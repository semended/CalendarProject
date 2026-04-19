from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.models import User


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
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_current_user_optional(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return user


def login_session(request: Request, user: User) -> None:
    request.session["user_id"] = user.id


def logout_session(request: Request) -> None:
    request.session.pop("user_id", None)
