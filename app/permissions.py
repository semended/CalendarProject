from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Task, TaskRole, TaskRolePermission, TaskUserRole

P_VIEW = "task.view"
P_EDIT_SETTINGS = "task.edit_settings"
P_MANAGE_MEMBERS = "task.manage_members"
P_MANAGE_SUBTASKS = "task.manage_subtasks"

# Обратно-совместимые алиасы для внешнего кода. Внутри has_permission
# проверка идёт по P_MANAGE_SUBTASKS — старые коды перенесены миграцией.
P_CREATE_SUBTASK = P_MANAGE_SUBTASKS
P_DELETE_SUBTASK = P_MANAGE_SUBTASKS

ALL_PERMS: List[str] = [
    P_VIEW,
    P_EDIT_SETTINGS,
    P_MANAGE_MEMBERS,
    P_MANAGE_SUBTASKS,
]

ROLE_DEFAULTS: Dict[str, List[str]] = {
    "Тимлид":      ALL_PERMS,
    "Менеджер":    [P_VIEW, P_EDIT_SETTINGS, P_MANAGE_SUBTASKS],
    "Разработчик": [P_VIEW, P_MANAGE_SUBTASKS],
}


async def ensure_role_permissions(db: AsyncSession, role: TaskRole) -> None:
    existing = await db.execute(
        select(TaskRolePermission).where(TaskRolePermission.task_role_id == role.id)
    )
    if existing.scalars().first() is not None:
        return
    defaults = ROLE_DEFAULTS.get(role.name, [P_VIEW])
    for p in defaults:
        db.add(TaskRolePermission(task_role_id=role.id, name=p, permission=p))
    await db.commit()


async def _find_role_in_task(
    db: AsyncSession, user_id: int, task_id: int
) -> Optional[TaskRole]:
    result = await db.execute(
        select(TaskUserRole)
        .options(selectinload(TaskUserRole.task_role).selectinload(TaskRole.permissions))
        .where(TaskUserRole.user_id == user_id, TaskUserRole.task_id == task_id)
    )
    tur = result.scalar_one_or_none()
    return tur.task_role if tur else None


async def has_permission(db: AsyncSession, user_id: int, task_id: int, perm: str) -> bool:
    cur_id: Optional[int] = task_id
    while cur_id is not None:
        role = await _find_role_in_task(db, user_id, cur_id)
        if role is not None:
            await ensure_role_permissions(db, role)
            # role.permissions уже подгружены через selectinload
            return any(p.permission == perm for p in role.permissions)
        task = await db.get(Task, cur_id)
        if task is None:
            break
        cur_id = task.parent_task_id
    return False


async def user_perms(db: AsyncSession, user_id: int, task_id: int) -> Dict[str, bool]:
    return {p: await has_permission(db, user_id, task_id, p) for p in ALL_PERMS}
