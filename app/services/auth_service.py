"""Аутентификация и регистрация — общий слой для cookie-сессий и JWT.

Роутеры (Jinja и /api/v1) идут сюда; здесь же сидит апгрейд legacy plaintext
→ bcrypt и обновление last_login_at. JWT-выпуск остаётся в роутере, потому что
это уже презентационная часть (роутер сам решает, отдавать ли куку или токен).
"""
from datetime import datetime
from typing import Optional

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.email import send_verification_email
from app.models import User
from app.security import hash_password, is_hashed, verify_password

# Jinja-форма регистрации шлёт голый Form(str) мимо RegisterRequest, поэтому
# формат email здесь проверяем сами — той же email-validator, что и EmailStr
# в /api/v1, чтобы правила не разъезжались между двумя UI-слоями.
_email_adapter = TypeAdapter(EmailStr)


class AuthError(Exception):
    """Общая ошибка авторизации."""


class InvalidCredentials(AuthError):
    """Неверная пара email/пароль."""


class UserAlreadyExists(AuthError):
    """Email уже занят."""


class InvalidEmail(AuthError):
    """Email синтаксически некорректен (например, `123@123`)."""


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    """Логин по email/паролю. Поднимает InvalidCredentials, если не сошлось.

    Побочный эффект: если в БД лежит plaintext (legacy от Flask), пересчитываем
    в bcrypt — старый пароль больше не должен прорастать.
    """
    user = await crud.get_user_by_email(db, email)
    if user is None or not verify_password(password, user.password):
        raise InvalidCredentials()
    if not is_hashed(user.password):
        await crud.update_user_password(db, user.id, hash_password(password))
    return user


async def register(
    db: AsyncSession,
    *,
    email: str,
    name: str,
    surname: str,
    password: str,
    patronymic: Optional[str] = None,
) -> User:
    """Создать пользователя и отправить письмо подтверждения.

    Поднимает InvalidEmail при некорректном формате почты,
    UserAlreadyExists — если email уже зарегистрирован.
    """
    try:
        # Возвращает нормализованную форму (lowercase домена и т.п.) —
        # её и сохраняем, чтобы lookup'ы по email были консистентны.
        email = _email_adapter.validate_python(email)
    except ValidationError:
        raise InvalidEmail()
    if await crud.get_user_by_email(db, email) is not None:
        raise UserAlreadyExists()
    user = await crud.add_user(
        db,
        email=email,
        name=name,
        surname=surname,
        password=hash_password(password),
        patronymic=patronymic,
    )
    send_verification_email(user.email, user.name)
    return user


async def record_login(db: AsyncSession, user: User) -> None:
    """Зафиксировать факт входа — обновить last_login_at.

    Поле появляется в миграции этапа 3; до её применения вызов — no-op.
    """
    if not hasattr(user, "last_login_at"):
        return
    # DB column хранит naive datetime, как и created_at — используем local
    # naive вместо UTC, чтобы не плодить разнобоя по таймзонам.
    user.last_login_at = datetime.now()
    db.add(user)
    await db.commit()
