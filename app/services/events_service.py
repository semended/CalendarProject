"""Запись доменных событий и уведомлений.

Точка входа для аудита и уведомлений: сервисы (task_service, auth_service)
вызывают эти функции при изменении состояния. UI пока не читает task_events
напрямую — модель/таблица заведены под будущую ленту активности и аналитику.
"""
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, TaskEvent

EVT_TASK_CREATED = "task.created"
EVT_TASK_STATE_CHANGED = "task.state_changed"
EVT_TASK_ASSIGNED = "task.assigned"
EVT_TASK_INFO_UPDATED = "task.info_updated"

NOTIF_TASK_ASSIGNED = "task_assigned"


async def record_task_event(
    db: AsyncSession,
    *,
    task_id: int,
    actor_user_id: Optional[int],
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> TaskEvent:
    event = TaskEvent(
        task_id=task_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def notify_user(
    db: AsyncSession,
    *,
    user_id: int,
    notification_type: str,
    task_id: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        task_id=task_id,
        notification_type=notification_type,
        payload=payload,
    )
    db.add(notif)
    await db.commit()
    await db.refresh(notif)
    return notif
