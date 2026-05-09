from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskRole, TaskRolePermission, TaskUserRole, User


# ----- users -----

async def add_user(
    db: AsyncSession,
    email: str,
    name: str,
    surname: str,
    password: str,
    patronymic: Optional[str] = None,
    bio: Optional[str] = None,
    position: Optional[str] = None,
    company: Optional[str] = None,
    workplace: Optional[str] = None,
    pronouns: Optional[str] = None,
    url: Optional[str] = None,
    confirmed: bool = False,
) -> User:
    user = User(
        email=email, name=name, surname=surname, patronymic=patronymic,
        password=password, bio=bio, position=position, company=company,
        workplace=workplace, pronouns=pronouns, url=url, confirmed=confirmed,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user(db: AsyncSession, user_id: int, user_dict: dict) -> Optional[User]:
    user = await db.get(User, user_id)
    if not user:
        return None

    allowed_fields = [
        "name", "surname", "patronymic", "email",
        "bio", "position", "company", "workplace", "pronouns", "url", "avatar_url",
        "privacy_email", "privacy_bio", "privacy_position", "privacy_company", "privacy_workplace",
    ]
    nullable = {"patronymic", "bio", "position", "company", "workplace", "pronouns", "avatar_url"}

    for key, value in user_dict.items():
        if key not in allowed_fields:
            continue
        if value is not None and value != "":
            setattr(user, key, value)
        elif key in nullable:
            setattr(user, key, None)
        elif key == "url":
            setattr(user, key, "https://example.com")

    await db.commit()
    await db.refresh(user)
    return user


async def update_user_avatar(db: AsyncSession, user_id: int, avatar_url: str) -> Optional[User]:
    user = await db.get(User, user_id)
    if not user:
        return None
    user.avatar_url = avatar_url
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_password(db: AsyncSession, user_id: int, hashed_password: str) -> None:
    user = await db.get(User, user_id)
    if user is None:
        return
    user.password = hashed_password
    await db.commit()


async def mark_user_confirmed(db: AsyncSession, user_id: int) -> None:
    user = await db.get(User, user_id)
    if user is None:
        return
    user.confirmed = True
    await db.commit()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    return await db.get(User, user_id)


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_all_users(db: AsyncSession) -> List[User]:
    result = await db.execute(select(User))
    return list(result.scalars().all())


# ----- tasks -----

async def create_task(
    db: AsyncSession,
    creator_id: int,
    name: str,
    description: str,
    color: str,
    duration: int,
    parent_task_id: Optional[int] = None,
    ended_at: Optional[datetime] = None,
    assignee_id: Optional[int] = None,
) -> Task:
    task = Task(
        creator_id=creator_id, parent_task_id=parent_task_id, name=name,
        description=description, color=color, duration=duration, ended_at=ended_at,
        assignee_id=assignee_id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def create_task_bundle(
    db: AsyncSession,
    creator_id: int,
    name: str,
    description: str,
    color: str,
    duration: int,
    parent_task_id: Optional[int] = None,
    ended_at: Optional[datetime] = None,
    assignee_id: Optional[int] = None,
) -> Task:
    from app.permissions import ensure_role_permissions

    task = await create_task(
        db, creator_id, name, description, color, duration, parent_task_id, ended_at, assignee_id
    )
    teamlead = await create_task_role(db, task.id, "Тимлид", is_system=True)
    manager = await create_task_role(db, task.id, "Менеджер", is_system=True)
    dev = await create_task_role(db, task.id, "Разработчик", is_system=True)
    for role in (teamlead, manager, dev):
        await ensure_role_permissions(db, role)
    await assign_user_to_task_role(db, creator_id, task.id, teamlead.id)
    return task


async def get_root_task(db: AsyncSession, task_id: int) -> Optional[Task]:
    task = await db.get(Task, task_id)
    while task is not None and task.parent_task_id is not None:
        task = await db.get(Task, task.parent_task_id)
    return task


async def get_assignee_candidates(
    db: AsyncSession, task_id: Optional[int], creator_id: int
) -> List[User]:
    """Кандидаты на assignee: участники корневого проекта + сам creator."""
    if task_id is None:
        u = await db.get(User, creator_id)
        return [u] if u else []
    root = await get_root_task(db, task_id)
    if root is None:
        u = await db.get(User, creator_id)
        return [u] if u else []
    return await get_users_in_task(db, root.id)


async def update_task_assignee(
    db: AsyncSession, task_id: int, assignee_id: Optional[int]
) -> Optional[Task]:
    task = await db.get(Task, task_id)
    if task is None:
        return None
    task.assignee_id = assignee_id
    await db.commit()
    await db.refresh(task)
    return task


async def update_task_state(db: AsyncSession, task_id: int, state: str) -> Optional[Task]:
    task = await db.get(Task, task_id)
    if task is None:
        return None
    task.state = state
    await db.commit()
    await db.refresh(task)
    return task


async def get_tasks_by_assignee(db: AsyncSession, user_id: int) -> List[Task]:
    result = await db.execute(select(Task).where(Task.assignee_id == user_id))
    return list(result.scalars().all())


async def get_task_by_id(db: AsyncSession, task_id: int) -> Optional[Task]:
    return await db.get(Task, task_id)


async def get_tasks_by_creator(db: AsyncSession, creator_id: int) -> List[Task]:
    result = await db.execute(select(Task).where(Task.creator_id == creator_id))
    return list(result.scalars().all())


async def get_tasks_by_user_id(
    db: AsyncSession,
    user_id: int,
    limit: Optional[int] = None,
    offset: int = 0,
    roots_only: bool = False,
) -> List[Task]:
    tur_result = await db.execute(
        select(TaskUserRole.task_id).where(TaskUserRole.user_id == user_id)
    )
    task_ids = {row for row in tur_result.scalars().all()}
    if not task_ids:
        return []
    stmt = select(Task).where(Task.id.in_(task_ids))
    if roots_only:
        stmt = stmt.where(Task.parent_task_id.is_(None))
    stmt = stmt.order_by(Task.id)
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_subtasks(
    db: AsyncSession,
    parent_task_id: int,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[Task]:
    stmt = (
        select(Task)
        .where(Task.parent_task_id == parent_task_id)
        .order_by(Task.id)
    )
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_task_info(
    db: AsyncSession,
    task_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    color: Optional[str] = None,
) -> Optional[Task]:
    task = await db.get(Task, task_id)
    if task is None:
        return None
    if name is not None:
        task.name = name
    if description is not None:
        task.description = description
    if color is not None:
        task.color = color
    await db.commit()
    await db.refresh(task)
    return task


async def update_task_deadline(
    db: AsyncSession, task_id: int, ended_at: Optional[datetime]
) -> Optional[Task]:
    """Изменить дедлайн задачи и пересчитать legacy-поле duration.

    duration хранится в секундах от created_at и осталось от Flask-схемы;
    мы пишем туда сами при изменении дедлайна, потому что server_default
    func.now() для created_at не пересчитывается, а UI-расчёты местами
    опираются на duration.
    """
    task = await db.get(Task, task_id)
    if task is None:
        return None
    task.ended_at = ended_at
    if ended_at is not None and task.created_at is not None:
        task.duration = max(0, int((ended_at - task.created_at).total_seconds()))
    await db.commit()
    await db.refresh(task)
    return task


# ----- roles -----

async def create_task_role(
    db: AsyncSession, task_id: int, name: str, is_system: bool = False
) -> TaskRole:
    task_role = TaskRole(task_id=task_id, name=name, is_system=is_system)
    db.add(task_role)
    await db.commit()
    await db.refresh(task_role)
    return task_role


async def add_permission_to_task_role(
    db: AsyncSession, task_role_id: int, name: str, permission: str
) -> TaskRolePermission:
    obj = TaskRolePermission(task_role_id=task_role_id, name=name, permission=permission)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def assign_user_to_task_role(
    db: AsyncSession, user_id: int, task_id: int, task_role_id: int
) -> TaskUserRole:
    assignment = TaskUserRole(user_id=user_id, task_id=task_id, task_role_id=task_role_id)
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def get_users_in_task(db: AsyncSession, task_id: int) -> List[User]:
    result = await db.execute(
        select(User)
        .join(TaskUserRole, User.id == TaskUserRole.user_id)
        .where(TaskUserRole.task_id == task_id)
    )
    return list(result.scalars().all())


async def get_user_role_in_task(
    db: AsyncSession, user_id: int, task_id: int
) -> Optional[str]:
    result = await db.execute(
        select(TaskRole.name)
        .join(TaskUserRole, TaskUserRole.task_role_id == TaskRole.id)
        .where(TaskUserRole.user_id == user_id, TaskUserRole.task_id == task_id)
    )
    return result.scalar_one_or_none()


