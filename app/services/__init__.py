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
from app.services.events_service import (
    EVT_TASK_ASSIGNED,
    EVT_TASK_CREATED,
    EVT_TASK_INFO_UPDATED,
    EVT_TASK_STATE_CHANGED,
    NOTIF_TASK_ASSIGNED,
    notify_user,
    record_task_event,
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
    "EVT_TASK_CREATED",
    "EVT_TASK_STATE_CHANGED",
    "EVT_TASK_ASSIGNED",
    "EVT_TASK_INFO_UPDATED",
    "NOTIF_TASK_ASSIGNED",
    "record_task_event",
    "notify_user",
]
