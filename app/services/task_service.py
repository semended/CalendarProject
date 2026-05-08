"""Создание/изменение задач и управление участниками.

Все правила (permissions, валидация assignee, расчёт duration из дедлайна,
наследование прав по дереву) живут здесь. Роутеры — тонкие.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models import Task, TaskUserRole, User
from app.permissions import (
    P_CREATE_SUBTASK,
    P_EDIT_SETTINGS,
    P_MANAGE_MEMBERS,
    has_permission,
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


# Sentinel для "duration без дедлайна" — legacy-поле требует не-NULL значения,
# воспроизводим Flask-овское поведение (создание задачи без дедлайна).
_NO_DEADLINE_DURATION = 2_147_000_000


class TaskServiceError(Exception):
    """База ошибок task_service."""


class PermissionDenied(TaskServiceError):
    """У пользователя нет требуемого права на эту таску (с учётом наследования)."""


class InvalidAssignee(TaskServiceError):
    """Этот юзер не входит в число кандидатов на assignee для данной таски."""


class TaskNotFound(TaskServiceError):
    """Запрошенная таска не существует."""


def _naive(dt: datetime) -> datetime:
    """DB хранит DateTime без tzinfo; tz-aware payloads нормализуем в local naive."""
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def _duration_from_deadline(ended_at: Optional[datetime]) -> int:
    if ended_at is None:
        return _NO_DEADLINE_DURATION
    return int((ended_at - datetime.now()).total_seconds())


async def _validate_assignee(
    db: AsyncSession,
    *,
    creator_id: int,
    parent_task_id: Optional[int],
    assignee_id: Optional[int],
) -> Optional[int]:
    """Проверить, что assignee_id входит в кандидатов корневого проекта.

    Возвращает валидированный assignee_id (или None, если кандидата нет).
    Не поднимает: вызывающий сам решает, что делать с None (HTML тихо сбрасывает,
    API возвращает 422 — но это уровень роутера).
    """
    if assignee_id is None:
        return None
    candidates = await crud.get_assignee_candidates(db, parent_task_id, creator_id)
    if not any(c.id == assignee_id for c in candidates):
        return None
    return assignee_id


async def create_task(
    db: AsyncSession,
    creator: User,
    *,
    name: str,
    description: str = "",
    color: str = "#0ea5e9",
    deadline: Optional[datetime] = None,
    parent_task_id: Optional[int] = None,
    assignee_id: Optional[int] = None,
    strict_assignee: bool = False,
) -> Task:
    """Создать задачу/подзадачу с проверкой прав и валидацией assignee.

    `strict_assignee=True` (для API) — невалидный assignee → InvalidAssignee.
    `strict_assignee=False` (для HTML) — невалидный assignee тихо сбрасывается.

    Триггерит создание стандартного набора ролей (Тимлид/Менеджер/Разработчик)
    с дефолтными правами и назначает creator-у роль Тимлида.
    """
    if parent_task_id is not None:
        if not await has_permission(db, creator.id, parent_task_id, P_CREATE_SUBTASK):
            raise PermissionDenied("Нет прав на создание подзадачи")

    deadline_naive = _naive(deadline) if deadline is not None else None
    duration = _duration_from_deadline(deadline_naive)

    validated_assignee = await _validate_assignee(
        db,
        creator_id=creator.id,
        parent_task_id=parent_task_id,
        assignee_id=assignee_id,
    )
    if assignee_id is not None and validated_assignee is None and strict_assignee:
        raise InvalidAssignee("Этот пользователь не может быть назначен на задачу")

    task = await crud.create_task_bundle(
        db,
        creator_id=creator.id,
        name=name.strip(),
        description=description.strip(),
        color=color,
        duration=duration,
        parent_task_id=parent_task_id,
        ended_at=deadline_naive,
        assignee_id=validated_assignee,
    )

    await record_task_event(
        db,
        task_id=task.id,
        actor_user_id=creator.id,
        event_type=EVT_TASK_CREATED,
        payload={
            "name": task.name,
            "parent_task_id": parent_task_id,
            "assignee_id": validated_assignee,
        },
    )
    if validated_assignee is not None and validated_assignee != creator.id:
        await notify_user(
            db,
            user_id=validated_assignee,
            notification_type=NOTIF_TASK_ASSIGNED,
            task_id=task.id,
            payload={"task_name": task.name, "by": creator.id},
        )

    return task


async def update_task(
    db: AsyncSession,
    user: User,
    task_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    color: Optional[str] = None,
    state: Optional[str] = None,
    assignee_id: Optional[int] = None,
    apply_assignee: bool = False,
    strict_assignee: bool = False,
) -> Task:
    """Изменить задачу. apply_assignee=True значит "перезаписать assignee на
    переданное значение" (включая None — снять). Это нужно потому, что для
    Pydantic v2 Optional не различает "не задано" и "null" — поэтому фактическое
    решение принимает роутер на основании model_fields_set / form-полей.
    """
    task = await crud.get_task_by_id(db, task_id)
    if task is None:
        raise TaskNotFound()
    if not await has_permission(db, user.id, task_id, P_EDIT_SETTINGS):
        raise PermissionDenied("Нет прав на редактирование задачи")

    info_changed = name is not None or description is not None or color is not None
    if info_changed:
        await crud.update_task_info(db, task_id, name, description, color)
        await record_task_event(
            db,
            task_id=task_id,
            actor_user_id=user.id,
            event_type=EVT_TASK_INFO_UPDATED,
            payload={
                k: v for k, v in {"name": name, "description": description, "color": color}.items()
                if v is not None
            },
        )

    if apply_assignee:
        validated_assignee = await _validate_assignee(
            db,
            creator_id=user.id,
            parent_task_id=task_id,
            assignee_id=assignee_id,
        )
        if assignee_id is not None and validated_assignee is None and strict_assignee:
            raise InvalidAssignee("Этот пользователь не может быть назначен на задачу")
        prev_assignee = task.assignee_id
        await crud.update_task_assignee(db, task_id, validated_assignee)
        if prev_assignee != validated_assignee:
            await record_task_event(
                db,
                task_id=task_id,
                actor_user_id=user.id,
                event_type=EVT_TASK_ASSIGNED,
                payload={"prev": prev_assignee, "new": validated_assignee},
            )
            if validated_assignee is not None and validated_assignee != user.id:
                await notify_user(
                    db,
                    user_id=validated_assignee,
                    notification_type=NOTIF_TASK_ASSIGNED,
                    task_id=task_id,
                    payload={"task_name": task.name, "by": user.id},
                )

    if state is not None and state != task.state:
        await crud.update_task_state(db, task_id, state)
        await record_task_event(
            db,
            task_id=task_id,
            actor_user_id=user.id,
            event_type=EVT_TASK_STATE_CHANGED,
            payload={"prev": task.state, "new": state},
        )

    refreshed = await crud.get_task_by_id(db, task_id)
    if refreshed is None:
        raise TaskNotFound()
    return refreshed


async def add_member(
    db: AsyncSession,
    actor: User,
    task_id: int,
    *,
    email: str,
    role_id: int,
) -> Optional[TaskUserRole]:
    """Добавить юзера на роль в проекте. Возвращает None, если email не найден
    (намеренно тихое поведение: не лит, что такого юзера нет).
    """
    if not await has_permission(db, actor.id, task_id, P_MANAGE_MEMBERS):
        raise PermissionDenied("Нет прав на управление участниками")
    target = await crud.get_user_by_email(db, email)
    if target is None:
        return None
    return await crud.assign_user_to_task_role(db, target.id, task_id, role_id)
