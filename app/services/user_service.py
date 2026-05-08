"""Профиль / пароль / аватар. Тонкая обёртка над crud — здесь тривиально мало
бизнес-логики, но держим единую точку входа на случай будущих эффектов
(например, событие в task_events при смене email).
"""
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models import User
from app.security import hash_password


async def update_profile(
    db: AsyncSession, user_id: int, profile: dict
) -> Optional[User]:
    """Обновить произвольный набор полей профиля + privacy. crud.update_user
    знает, какие ключи разрешены и какие являются nullable.
    """
    return await crud.update_user(db, user_id, profile)


async def update_password(db: AsyncSession, user_id: int, new_password: str) -> None:
    """Сменить пароль (хешируется здесь, plaintext в БД больше не пишем)."""
    await crud.update_user_password(db, user_id, hash_password(new_password))


async def update_avatar(
    db: AsyncSession, user_id: int, avatar_token: str
) -> Optional[User]:
    """Записать avatar_url. Файловые операции делает роутер — он же отвечает
    за валидацию формата, сохранение байтов и удаление старого файла.
    """
    return await crud.update_user_avatar(db, user_id, avatar_token)
