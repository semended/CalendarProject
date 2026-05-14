"""Управление ролями проекта — создание/редактирование/удаление кастомных ролей.

Системные роли (is_system=True) — Тимлид/Менеджер/Разработчик — нельзя удалить
и переименовать, но их набор прав можно менять (например, отнять у Менеджера
право управлять участниками). Это даёт гибкость на учебных проектах,
но не разрушает дефолтную структуру.
"""
from typing import Iterable, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Task, TaskRole, TaskRolePermission, TaskUserRole, User
from app.permissions import (
    ALL_PERMS,
    P_MANAGE_MEMBERS,
    has_permission,
)


class RolesServiceError(Exception):
    pass


class PermissionDenied(RolesServiceError):
    pass


class RoleNotFound(RolesServiceError):
    pass


class SystemRoleProtected(RolesServiceError):
    """Попытка удалить или переименовать системную роль."""


class InvalidRoleName(RolesServiceError):
    pass


def _validated_perms(perms: Iterable[str]) -> List[str]:
    """Оставляем только известные коды прав. Неизвестные молча отбрасываем
    (форма из браузера может прислать что угодно)."""
    return [p for p in perms if p in ALL_PERMS]


async def list_roles(db: AsyncSession, task_id: int) -> List[TaskRole]:
    """Роли задачи и предков, c подгруженными permissions."""
    roles: List[TaskRole] = []
    cur_id = task_id
    while cur_id is not None:
        result = await db.execute(
            select(TaskRole)
            .options(selectinload(TaskRole.permissions))
            .where(TaskRole.task_id == cur_id)
            .order_by(TaskRole.is_system.desc(), TaskRole.id)
        )
        roles.extend(result.scalars().all())
        task = await db.get(Task, cur_id)
        if task is None:
            break
        cur_id = task.parent_task_id
    return roles


async def _reload_role_with_perms(db: AsyncSession, role_id: int) -> TaskRole:
    """Перечитать роль с подгруженными permissions — после изменений мы
    возвращаем эту структуру наверх (роутер сериализует), а лениво в async
    relationship загружаться не может (MissingGreenlet)."""
    result = await db.execute(
        select(TaskRole)
        .options(selectinload(TaskRole.permissions))
        .where(TaskRole.id == role_id)
    )
    return result.scalar_one()


async def create_custom_role(
    db: AsyncSession,
    actor: User,
    task_id: int,
    *,
    name: str,
    permissions: Iterable[str],
) -> TaskRole:
    if not await has_permission(db, actor.id, task_id, P_MANAGE_MEMBERS):
        raise PermissionDenied("Нет прав на управление ролями проекта")
    name = (name or "").strip()
    if not name:
        raise InvalidRoleName("Название роли не может быть пустым")

    role = TaskRole(task_id=task_id, name=name, is_system=False)
    db.add(role)
    await db.flush()
    for code in _validated_perms(permissions):
        db.add(TaskRolePermission(task_role_id=role.id, name=code, permission=code))
    await db.commit()
    return await _reload_role_with_perms(db, role.id)


async def update_role(
    db: AsyncSession,
    actor: User,
    role_id: int,
    *,
    name: str | None = None,
    permissions: Iterable[str] | None = None,
) -> TaskRole:
    result = await db.execute(
        select(TaskRole)
        .options(selectinload(TaskRole.permissions))
        .where(TaskRole.id == role_id)
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise RoleNotFound()
    if not await has_permission(db, actor.id, role.task_id, P_MANAGE_MEMBERS):
        raise PermissionDenied("Нет прав на управление ролями проекта")

    if name is not None:
        new_name = name.strip()
        if not new_name:
            raise InvalidRoleName("Название роли не может быть пустым")
        if role.is_system and new_name != role.name:
            raise SystemRoleProtected("Системную роль нельзя переименовать")
        role.name = new_name

    if permissions is not None:
        wanted = set(_validated_perms(permissions))
        existing = {p.permission for p in role.permissions}
        to_remove = existing - wanted
        to_add = wanted - existing
        if to_remove:
            await db.execute(
                TaskRolePermission.__table__.delete().where(
                    TaskRolePermission.task_role_id == role.id,
                    TaskRolePermission.permission.in_(to_remove),
                )
            )
        for code in to_add:
            db.add(TaskRolePermission(task_role_id=role.id, name=code, permission=code))

    await db.commit()
    # SessionLocal у нас expire_on_commit=False, поэтому после commit лежит
    # stale collection role.permissions. Явно сбрасываем, чтобы reload подгрузил
    # из БД актуальное состояние, а не из identity-map'а.
    db.expire(role, ["permissions"])
    return await _reload_role_with_perms(db, role.id)


async def delete_role(db: AsyncSession, actor: User, role_id: int) -> None:
    role = await db.get(TaskRole, role_id)
    if role is None:
        raise RoleNotFound()
    if not await has_permission(db, actor.id, role.task_id, P_MANAGE_MEMBERS):
        raise PermissionDenied("Нет прав на управление ролями проекта")
    if role.is_system:
        raise SystemRoleProtected("Системную роль нельзя удалить")

    # Снимаем назначения юзеров на эту роль (cascade сделал бы то же,
    # но явно — чтобы изменение поведения миграции не сломало процесс).
    await db.execute(
        TaskUserRole.__table__.delete().where(TaskUserRole.task_role_id == role.id)
    )
    await db.delete(role)
    await db.commit()
