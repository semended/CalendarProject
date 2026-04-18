from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Task, TaskRole, TaskRolePermission, TaskUserRole

P_VIEW = "task.view"
P_EDIT_SETTINGS = "task.edit_settings"
P_MANAGE_MEMBERS = "task.manage_members"
P_CREATE_SUBTASK = "task.create_subtask"
P_DELETE_SUBTASK = "task.delete_subtask"

ALL_PERMS: List[str] = [
    P_VIEW,
    P_EDIT_SETTINGS,
    P_MANAGE_MEMBERS,
    P_CREATE_SUBTASK,
    P_DELETE_SUBTASK,
]

ROLE_DEFAULTS: Dict[str, List[str]] = {
    "Тимлид":      ALL_PERMS,
    "Менеджер":    [P_VIEW, P_EDIT_SETTINGS, P_CREATE_SUBTASK, P_DELETE_SUBTASK],
    "Разработчик": [P_VIEW, P_CREATE_SUBTASK],
}


def ensure_role_permissions(db: Session, role: TaskRole) -> None:
    if role.permissions:
        return
    defaults = ROLE_DEFAULTS.get(role.name, [P_VIEW])
    for p in defaults:
        db.add(TaskRolePermission(task_role_id=role.id, name=p, permission=p))
    db.commit()
    db.refresh(role)


def _find_role_in_task(db: Session, user_id: int, task_id: int) -> Optional[TaskRole]:
    tur = (
        db.query(TaskUserRole)
        .filter(TaskUserRole.user_id == user_id, TaskUserRole.task_id == task_id)
        .first()
    )
    return tur.task_role if tur else None


def has_permission(db: Session, user_id: int, task_id: int, perm: str) -> bool:
    cur_id: Optional[int] = task_id
    while cur_id is not None:
        role = _find_role_in_task(db, user_id, cur_id)
        if role is not None:
            ensure_role_permissions(db, role)
            return any(p.permission == perm for p in role.permissions)
        task = db.get(Task, cur_id)
        if task is None:
            break
        cur_id = task.parent_task_id
    return False


def user_perms(db: Session, user_id: int, task_id: int) -> Dict[str, bool]:
    return {p: has_permission(db, user_id, task_id, p) for p in ALL_PERMS}
