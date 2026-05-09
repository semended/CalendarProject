from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Index, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    surname = Column(String(255), nullable=False)
    patronymic = Column(String(255), nullable=True)
    password = Column(String(255), nullable=False)
    bio = Column(String(500), nullable=True)
    position = Column(String(255), nullable=True)
    company = Column(String(255), nullable=True)
    workplace = Column(String(255), nullable=True)
    pronouns = Column(String(50), nullable=True)
    url = Column(String(255), nullable=True)
    avatar_url = Column(String(255), nullable=True)
    confirmed = Column(Boolean, nullable=False, default=False)
    privacy_email     = Column(String(16), nullable=False, server_default="self")
    privacy_bio       = Column(String(16), nullable=False, server_default="authed")
    privacy_position  = Column(String(16), nullable=False, server_default="authed")
    privacy_company   = Column(String(16), nullable=False, server_default="authed")
    privacy_workplace = Column(String(16), nullable=False, server_default="authed")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    last_login_at = Column(DateTime, nullable=True)

    created_tasks = relationship("Task", back_populates="creator", foreign_keys="Task.creator_id")
    task_roles = relationship("TaskUserRole", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', name='{self.name} {self.surname}')>"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    parent_task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    creator_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    assignee_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    color = Column(Text, nullable=False)
    duration = Column(BigInteger, nullable=False)
    state = Column(String(20), nullable=False, server_default="todo")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)

    creator = relationship("User", back_populates="created_tasks", foreign_keys=[creator_id])
    assignee = relationship("User", foreign_keys=[assignee_id])
    parent_task = relationship("Task", remote_side=[id], back_populates="subtasks")
    subtasks = relationship("Task", back_populates="parent_task")
    task_roles = relationship("TaskRole", back_populates="task")
    user_roles = relationship("TaskUserRole", back_populates="task")

    @property
    def status(self) -> str:
        from datetime import datetime
        if self.state == "done":
            return "completed"
        if self.state == "paused":
            return "paused"
        if self.ended_at is not None and self.ended_at < datetime.now():
            return "overdue"
        return "active"

    def __repr__(self):
        return f"<Task(id={self.id}, name='{self.name}', creator_id={self.creator_id})>"


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    start_at = Column(DateTime, nullable=False)
    end_at = Column(DateTime, nullable=False)
    kind = Column(String(20), nullable=False, server_default="busy")
    note = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    user = relationship("User")

    __table_args__ = (
        Index("availability_slots_user_start_idx", "user_id", "start_at"),
    )

    def __repr__(self):
        return f"<AvailabilitySlot(id={self.id}, user_id={self.user_id}, {self.start_at}→{self.end_at}, {self.kind})>"


class TaskRole(Base):
    __tablename__ = "task_roles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    # is_system=True — это дефолтная роль, созданная при создании проекта
    # (Тимлид/Менеджер/Разработчик). Нельзя удалить/переименовать, права
    # менять можно. Кастомные роли — is_system=False.
    is_system = Column(Boolean, nullable=False, server_default="false")

    task = relationship("Task", back_populates="task_roles")
    permissions = relationship("TaskRolePermission", back_populates="task_role", cascade="all, delete-orphan")
    user_roles = relationship("TaskUserRole", back_populates="task_role")

    def __repr__(self):
        return f"<TaskRole(id={self.id}, name='{self.name}', task_id={self.task_id})>"


class TaskRolePermission(Base):
    __tablename__ = "task_role_permissions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_role_id = Column(BigInteger, ForeignKey("task_roles.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    permission = Column(String(255), nullable=False)

    task_role = relationship("TaskRole", back_populates="permissions")

    def __repr__(self):
        return f"<TaskRolePermission(id={self.id}, name='{self.name}', permission='{self.permission}')>"


class TaskUserRole(Base):
    __tablename__ = "task_user_roles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    task_role_id = Column(BigInteger, ForeignKey("task_roles.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    user = relationship("User", back_populates="task_roles")
    task = relationship("Task", back_populates="user_roles")
    task_role = relationship("TaskRole", back_populates="user_roles")

    __table_args__ = (
        UniqueConstraint("user_id", "task_id", "task_role_id", name="task_user_roles_unique"),
        Index("task_user_roles_user_id_index", "user_id"),
        Index("task_user_roles_task_id_index", "task_id"),
        Index("task_user_roles_task_role_id_index", "task_role_id"),
    )

    def __repr__(self):
        return f"<TaskUserRole(id={self.id}, user_id={self.user_id}, task_id={self.task_id}, task_role_id={self.task_role_id})>"


class TaskEvent(Base):
    """История бизнес-событий по задаче (создание, смена статуса, assign, ...).

    Пишется из task_service. Не связана с UI напрямую — данные нужны для
    аудита, аналитики и будущих лент активности.
    """
    __tablename__ = "task_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    task = relationship("Task")
    actor = relationship("User")

    __table_args__ = (
        Index("task_events_task_id_idx", "task_id"),
        Index("task_events_created_at_idx", "created_at"),
    )

    def __repr__(self):
        return f"<TaskEvent(id={self.id}, task_id={self.task_id}, type='{self.event_type}')>"


class TaskComment(Base):
    """Комментарии к задачам. UI пока нет; модель и API готовы для расширения."""
    __tablename__ = "task_comments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    author_user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True)

    task = relationship("Task")
    author = relationship("User")

    __table_args__ = (
        Index("task_comments_task_id_idx", "task_id"),
    )

    def __repr__(self):
        return f"<TaskComment(id={self.id}, task_id={self.task_id}, author_user_id={self.author_user_id})>"


class Notification(Base):
    """Уведомления пользователю — назначение задачи, упоминание, смена статуса.

    read_at = NULL → непрочитано. Связь с задачей опциональная (SET NULL),
    чтобы удаление задачи не тащило за собой уведомления.
    """
    __tablename__ = "notifications"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    notification_type = Column(String(64), nullable=False)
    payload = Column(JSONB, nullable=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])
    task = relationship("Task", foreign_keys=[task_id])

    __table_args__ = (
        Index("notifications_user_unread_idx", "user_id", "read_at"),
        Index("notifications_created_at_idx", "created_at"),
    )

    def __repr__(self):
        return f"<Notification(id={self.id}, user_id={self.user_id}, type='{self.notification_type}')>"
