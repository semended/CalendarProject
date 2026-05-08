"""Сервисный слой — единый источник бизнес-логики для Jinja-роутов и /api/v1.

Сервисы возвращают доменные объекты или поднимают типизированные исключения
(`AuthError`, `TaskServiceError`). Роутеры транслируют их в HTML/JSON-ответы:
HTTPException для API, TemplateResponse с error для Jinja.
"""
from app.services.auth_service import (
    AuthError,
    InvalidCredentials,
    UserAlreadyExists,
    authenticate,
    record_login,
    register,
)
from app.services.task_service import (
    InvalidAssignee,
    PermissionDenied,
    TaskNotFound,
    TaskServiceError,
    add_member,
    create_task,
    update_task,
)
from app.services.user_service import (
    update_avatar,
    update_password,
    update_profile,
)

__all__ = [
    "AuthError",
    "InvalidCredentials",
    "UserAlreadyExists",
    "authenticate",
    "record_login",
    "register",
    "TaskServiceError",
    "PermissionDenied",
    "InvalidAssignee",
    "TaskNotFound",
    "create_task",
    "update_task",
    "add_member",
    "update_avatar",
    "update_password",
    "update_profile",
]
