# 1. Установить PostgreSQL и поднять его сервис
# 2. Подтянуть все нужные пакеты для исполнения скрипта
# 3. Выполнить команду: createdb testdb
# 4. Запустить скрипт

from sqlalchemy import create_engine, Column, BigInteger, String, Boolean, DateTime, Text, ForeignKey, Index, \
    text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional, List

DATABASE_URL = "postgresql+psycopg2://postgres:123@localhost:5432/testdb"

engine = create_engine(DATABASE_URL, echo=True)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)


# Модели
class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    surname = Column(String(255), nullable=False)
    patronymic = Column(String(255), nullable=True)
    password = Column(String(255), nullable=False)
    bio = Column(String(500), nullable=True)  # Изменен тип на String(500)
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
    duration = Column(BigInteger, nullable=False)  # Длительность в секундах
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


# Функции для работы с базой данных
def init_db():
    """Инициализация базы данных - создание всех таблиц"""
    Base.metadata.create_all(engine)
    print("База данных инициализирована")


# Функции для работы с пользователями
def add_user(email: str,
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
             confirmed: Optional[bool] = False) -> User:
    """Создание нового пользователя"""
    session = SessionLocal()

    try:
        user = User(
            email=email,
            name=name,
            surname=surname,
            patronymic=patronymic,
            password=password,
            bio=bio,
            position=position,
            company=company,
            workplace=workplace,
            pronouns=pronouns,
            url=url,
            confirmed=confirmed
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def update_user(user_id: int, user_dict: dict) -> Optional[User]:
    """Обновление данных пользователя"""
    session = SessionLocal()

    try:
        user = session.get(User, user_id)
        if not user:
            return None

        # Обновляем только те поля, которые есть в словаре и разрешены
        allowed_fields = [
            'name', 'surname', 'patronymic', 'email',
            'bio', 'position', 'company', 'workplace', 'pronouns', 'url', 'avatar_url'
        ]

        for key, value in user_dict.items():
            if key in allowed_fields and hasattr(user, key):
                if value is not None and value != '':
                    setattr(user, key, value)
                elif key in ['patronymic', 'bio', 'position', 'company', 'workplace', 'pronouns', 'avatar_url']:
                    # Поля, которые могут быть None
                    setattr(user, key, None)
                elif key == 'url' and (value is None or value == ''):
                    setattr(user, key, 'https://example.com')

        session.commit()
        session.refresh(user)
        return user
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def update_user_avatar(user_id: int, avatar_url: str) -> Optional[User]:
    """Обновление аватара пользователя"""
    session = SessionLocal()

    try:
        user = session.get(User, user_id)
        if not user:
            return None

        user.avatar_url = avatar_url
        session.commit()
        session.refresh(user)
        return user
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def get_user_role_in_task(user_id: int, task_id: int) -> Optional[str]:
    """Получение названия роли пользователя в задаче"""
    session = SessionLocal()

    # Находим связь пользователя с задачей
    task_user_role = session.query(TaskUserRole).filter(
        TaskUserRole.user_id == user_id,
        TaskUserRole.task_id == task_id
    ).first()

    role_name = None
    if task_user_role and task_user_role.task_role:
        role_name = task_user_role.task_role.name

    session.close()
    return role_name


def get_user_by_id(user_id: int) -> Optional[User]:
    """Получение пользователя по ID"""
    session = SessionLocal()
    user = session.get(User, user_id)
    session.close()
    return user


def get_user_by_email(email: str) -> Optional[User]:
    """Получение пользователя по email"""
    session = SessionLocal()
    user = session.query(User).filter(User.email == email).first()
    session.close()
    return user


def get_all_users() -> List[User]:
    """Получение всех пользователей"""
    session = SessionLocal()
    users = session.query(User).all()
    session.close()
    return users


# Функции для работы с задачами
def create_task(
        creator_id: int,
        name: str,
        description: str,
        color: str,
        duration: int,  # Длительность в секундах
        parent_task_id: Optional[int] = None,
        ended_at: Optional[datetime] = None
) -> Task:
    """Создание новой задачи"""
    session = SessionLocal()

    try:
        task = Task(
            creator_id=creator_id,
            parent_task_id=parent_task_id,
            name=name,
            description=description,
            color=color,
            duration=duration,
            ended_at=ended_at
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        return task
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def create_task_bundle(creator_id: int,
                       name: str,
                       description: str,
                       color: str,
                       duration: int,  # Длительность в секундах
                       parent_task_id: Optional[int] = None,
                       ended_at: Optional[datetime] = None):
    task = create_task(creator_id, name, description, color, duration, parent_task_id, ended_at)
    teamlead = create_task_role(task.id, 'Тимлид')
    create_task_role(task.id, 'Менеджер')
    create_task_role(task.id, 'Разработчик')
    assign_user_to_task_role(creator_id, task.id, teamlead.id)


def get_task_by_id(task_id: int) -> Optional[Task]:
    """Получение задачи по ID"""
    session = SessionLocal()
    task = session.get(Task, task_id)
    session.close()
    return task


def get_tasks_by_creator(creator_id: int) -> List[Task]:
    """Получение всех задач созданных пользователем"""
    session = SessionLocal()
    tasks = session.query(Task).filter(Task.creator_id == creator_id).all()
    session.close()
    return tasks


def get_tasks_by_user_id(user_id: int) -> List[Task]:
    """Получение всех задач, где пользователь имеет роль в TaskUserRole"""
    session = SessionLocal()

    task_user_roles = session.query(TaskUserRole).filter(
        TaskUserRole.user_id == user_id
    ).all()

    task_ids = {tur.task_id for tur in task_user_roles}
    tasks = session.query(Task).filter(Task.id.in_(task_ids)).all()

    session.close()
    return tasks


def get_subtasks(parent_task_id: int) -> List[Task]:
    """Получение всех подзадач родительской задачи"""
    session = SessionLocal()
    tasks = session.query(Task).filter(Task.parent_task_id == parent_task_id).all()
    session.close()
    return tasks


def update_task_info(
  task_id: int,
  name: Optional[str] = None,
  description: Optional[str] = None,
  color: Optional[str] = None
) -> Optional[Task]:
    """Обновление информации о задаче по ID"""
    session = SessionLocal()

    # Находим задачу по ID
    task = session.query(Task).filter(Task.id == task_id).first()

    if task:
        # Обновляем только переданные поля
        if name is not None:
            task.name = name
        if description is not None:
            task.description = description
        if color is not None:
            task.color = color

        session.commit()
        session.refresh(task)

    session.close()
    return task


def update_task_status(
        task_id: int,
        ended_at: Optional[datetime] = None
) -> Optional[Task]:
    """Обновление статуса задачи (завершение)"""
    session = SessionLocal()

    try:
        task = session.get(Task, task_id)
        if not task:
            return None

        if ended_at is not None:
            task.ended_at = ended_at

        session.commit()
        session.refresh(task)
        return task
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


# Функции для работы с ролями в задачах
def create_task_role(
        task_id: int,
        name: str
) -> TaskRole:
    """Создание новой роли для задачи"""
    session = SessionLocal()

    try:
        task_role = TaskRole(
            task_id=task_id,
            name=name
        )
        session.add(task_role)
        session.commit()
        session.refresh(task_role)
        return task_role
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def add_permission_to_task_role(
        task_role_id: int,
        name: str,
        permission: str
) -> TaskRolePermission:
    """Добавление разрешения к роли в задаче"""
    session = SessionLocal()

    try:
        permission_obj = TaskRolePermission(
            task_role_id=task_role_id,
            name=name,
            permission=permission
        )
        session.add(permission_obj)
        session.commit()
        session.refresh(permission_obj)
        return permission_obj
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def assign_user_to_task_role(
        user_id: int,
        task_id: int,
        task_role_id: int
) -> TaskUserRole:
    """Назначение пользователя на роль в задаче"""
    session = SessionLocal()

    try:
        assignment = TaskUserRole(
            user_id=user_id,
            task_id=task_id,
            task_role_id=task_role_id
        )
        session.add(assignment)
        session.commit()
        session.refresh(assignment)
        return assignment
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def get_users_in_task(task_id: int) -> List[User]:
    """Получение всех пользователей, назначенных на задачу"""
    session = SessionLocal()

    users = (
        session.query(User)
        .join(TaskUserRole, User.id == TaskUserRole.user_id)
        .filter(TaskUserRole.task_id == task_id)
        .all()
    )

    session.close()
    return users


def get_tasks_for_user(user_id: int) -> List[Task]:
    """Получение всех задач, в которых участвует пользователь"""
    session = SessionLocal()

    tasks = (
        session.query(Task)
        .join(TaskUserRole, Task.id == TaskUserRole.task_id)
        .filter(TaskUserRole.user_id == user_id)
        .all()
    )

    session.close()
    return tasks


# Утилитные функции
def drop_all_tables():
    """Удаление всех таблиц (осторожно!)"""
    Base.metadata.drop_all(engine)
    print("Все таблицы удалены")


def recreate_database():
    """Пересоздание всей базы данных"""
    drop_all_tables()
    init_db()
    print("База данных пересоздана")


# Пример использования
if __name__ == '__main__':
    # Инициализация базы данных
    init_db()
