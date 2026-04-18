from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Task, TaskRole, TaskRolePermission, TaskUserRole, User


# ----- users -----

def add_user(
    db: Session,
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
    db.commit()
    db.refresh(user)
    return user


def update_user(db: Session, user_id: int, user_dict: dict) -> Optional[User]:
    user = db.get(User, user_id)
    if not user:
        return None

    allowed_fields = [
        "name", "surname", "patronymic", "email",
        "bio", "position", "company", "workplace", "pronouns", "url", "avatar_url",
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

    db.commit()
    db.refresh(user)
    return user


def update_user_avatar(db: Session, user_id: int, avatar_url: str) -> Optional[User]:
    user = db.get(User, user_id)
    if not user:
        return None
    user.avatar_url = avatar_url
    db.commit()
    db.refresh(user)
    return user


def update_user_password(db: Session, user_id: int, hashed_password: str) -> None:
    user = db.get(User, user_id)
    if user is None:
        return
    user.password = hashed_password
    db.commit()


def mark_user_confirmed(db: Session, user_id: int) -> None:
    user = db.get(User, user_id)
    if user is None:
        return
    user.confirmed = True
    db.commit()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def get_all_users(db: Session) -> List[User]:
    return db.query(User).all()


# ----- tasks -----

def create_task(
    db: Session,
    creator_id: int,
    name: str,
    description: str,
    color: str,
    duration: int,
    parent_task_id: Optional[int] = None,
    ended_at: Optional[datetime] = None,
) -> Task:
    task = Task(
        creator_id=creator_id, parent_task_id=parent_task_id, name=name,
        description=description, color=color, duration=duration, ended_at=ended_at,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def create_task_bundle(
    db: Session,
    creator_id: int,
    name: str,
    description: str,
    color: str,
    duration: int,
    parent_task_id: Optional[int] = None,
    ended_at: Optional[datetime] = None,
) -> Task:
    from app.permissions import ensure_role_permissions

    task = create_task(db, creator_id, name, description, color, duration, parent_task_id, ended_at)
    teamlead = create_task_role(db, task.id, "Тимлид")
    manager = create_task_role(db, task.id, "Менеджер")
    dev = create_task_role(db, task.id, "Разработчик")
    for role in (teamlead, manager, dev):
        ensure_role_permissions(db, role)
    assign_user_to_task_role(db, creator_id, task.id, teamlead.id)
    return task


def get_task_by_id(db: Session, task_id: int) -> Optional[Task]:
    return db.get(Task, task_id)


def get_tasks_by_creator(db: Session, creator_id: int) -> List[Task]:
    return db.query(Task).filter(Task.creator_id == creator_id).all()


def get_tasks_by_user_id(db: Session, user_id: int) -> List[Task]:
    task_ids = {
        tur.task_id
        for tur in db.query(TaskUserRole).filter(TaskUserRole.user_id == user_id).all()
    }
    if not task_ids:
        return []
    return db.query(Task).filter(Task.id.in_(task_ids)).all()


def get_subtasks(db: Session, parent_task_id: int) -> List[Task]:
    return db.query(Task).filter(Task.parent_task_id == parent_task_id).all()


def update_task_info(
    db: Session,
    task_id: int,
    name: Optional[str] = None,
    description: Optional[str] = None,
    color: Optional[str] = None,
) -> Optional[Task]:
    task = db.query(Task).filter(Task.id == task_id).first()
    if task is None:
        return None
    if name is not None:
        task.name = name
    if description is not None:
        task.description = description
    if color is not None:
        task.color = color
    db.commit()
    db.refresh(task)
    return task


def update_task_status(db: Session, task_id: int, ended_at: Optional[datetime] = None) -> Optional[Task]:
    task = db.get(Task, task_id)
    if task is None:
        return None
    if ended_at is not None:
        task.ended_at = ended_at
    db.commit()
    db.refresh(task)
    return task


# ----- roles -----

def create_task_role(db: Session, task_id: int, name: str) -> TaskRole:
    task_role = TaskRole(task_id=task_id, name=name)
    db.add(task_role)
    db.commit()
    db.refresh(task_role)
    return task_role


def add_permission_to_task_role(db: Session, task_role_id: int, name: str, permission: str) -> TaskRolePermission:
    obj = TaskRolePermission(task_role_id=task_role_id, name=name, permission=permission)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def assign_user_to_task_role(db: Session, user_id: int, task_id: int, task_role_id: int) -> TaskUserRole:
    assignment = TaskUserRole(user_id=user_id, task_id=task_id, task_role_id=task_role_id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def get_users_in_task(db: Session, task_id: int) -> List[User]:
    return (
        db.query(User)
        .join(TaskUserRole, User.id == TaskUserRole.user_id)
        .filter(TaskUserRole.task_id == task_id)
        .all()
    )


def get_user_role_in_task(db: Session, user_id: int, task_id: int) -> Optional[str]:
    tur = (
        db.query(TaskUserRole)
        .filter(TaskUserRole.user_id == user_id, TaskUserRole.task_id == task_id)
        .first()
    )
    if tur and tur.task_role:
        return tur.task_role.name
    return None


def init_db() -> None:
    from app.database import Base, engine
    Base.metadata.create_all(engine)
