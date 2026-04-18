from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Index, String, Text,
    UniqueConstraint,
)
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
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    created_tasks = relationship("Task", back_populates="creator")
    task_roles = relationship("TaskUserRole", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', name='{self.name} {self.surname}')>"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    parent_task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    creator_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    color = Column(Text, nullable=False)
    duration = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)

    creator = relationship("User", back_populates="created_tasks")
    parent_task = relationship("Task", remote_side=[id], back_populates="subtasks")
    subtasks = relationship("Task", back_populates="parent_task")
    task_roles = relationship("TaskRole", back_populates="task")
    user_roles = relationship("TaskUserRole", back_populates="task")

    def __repr__(self):
        return f"<Task(id={self.id}, name='{self.name}', creator_id={self.creator_id})>"


class TaskRole(Base):
    __tablename__ = "task_roles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)

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
