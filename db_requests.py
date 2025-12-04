# 1. Установить PostgreSQL и поднять его сервис
# 2. Подтянуть все нужные пакеты для исполнения скрипта
# 3. Выполнить команду: createdb testdb
# 4. Запустить скрипт

from sqlalchemy import create_engine, Column, BigInteger, String, Boolean, DateTime, Float, Text, ForeignKey, Index, \
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
class Role(Base):
    __tablename__ = "roles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    slug = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)

    users = relationship("User", back_populates="role")

    def __repr__(self):
        return f"<Role(id={self.id}, slug='{self.slug}', name='{self.name}')>"


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    slug = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    surname = Column(String(255), nullable=False)
    patronymic = Column(String(255), nullable=True)
    password = Column(String(255), nullable=False)
    role_id = Column(BigInteger, ForeignKey("roles.id"), nullable=False)
    avatar_url = Column(String(255), nullable=False, default="")
    confirmed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    role = relationship("Role", back_populates="users")
    created_tasks = relationship("Task", back_populates="creator")
    task_roles = relationship("TaskUserRole", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', name='{self.name} {self.surname}')>"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    parent_task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    creator_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    color = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(BigInteger, nullable=False)
    grade = Column(Float, nullable=False)
    story_points = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    paused_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

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
    slug = Column(String(255), nullable=False)
    task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)

    task = relationship("Task", back_populates="task_roles")
    permissions = relationship("TaskRolePermission", back_populates="task_role", cascade="all, delete-orphan")
    user_roles = relationship("TaskUserRole", back_populates="task_role")

    __table_args__ = (
        Index("task_roles_slug_index", "slug"),
    )

    def __repr__(self):
        return f"<TaskRole(id={self.id}, slug='{self.slug}', name='{self.name}', task_id={self.task_id})>"


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
    #print("База данных инициализирована")


def add_initial_roles():
    """Добавление начальных ролей в систему"""
    session = SessionLocal()

    # Проверяем, есть ли уже роли
    existing_roles = session.query(Role).count()

    if existing_roles == 0:
        roles = [
            Role(slug='teamlead', name='Тимлид'),
            Role(slug='manager', name='Менеджер'),
            Role(slug='developer', name='Разработчик'),
        ]
        session.add_all(roles)
        session.commit()
        #print("Добавлены начальные роли")
    else:
        pass
        #print("Роли уже существуют")

    session.close()


# Функции для работы с пользователями
def add_user(user_dict) -> User:
    """Создание нового пользователя"""
    session = SessionLocal()

    try:
        user = User(
            slug=user_dict['slug'],
            email=user_dict['email'],
            name=user_dict['name'],
            surname=user_dict['surname'],
            patronymic=user_dict['patronymic'],
            password=user_dict['password'],
            role_id=user_dict['role_id'],
            avatar_url=user_dict['avatar_url'],
            confirmed=user_dict['confirmed']
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


def get_user_by_id(user_id: int) -> Optional[User]:
    """Получение пользователя по ID"""
    session = SessionLocal()
    user = session.get(User, user_id)
    session.close()
    return user


def get_user_by_slug(slug: str) -> Optional[User]:
    """Получение пользователя по slug"""
    session = SessionLocal()
    user = session.query(User).filter(User.slug == slug).first()
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


# Функции для работы с ролями
def create_role(slug: str, name: str) -> Role:
    """Создание новой роли в системе"""
    session = SessionLocal()

    try:
        role = Role(slug=slug, name=name)
        session.add(role)
        session.commit()
        session.refresh(role)
        return role
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def get_role_by_id(role_id: int) -> Optional[Role]:
    """Получение роли по ID"""
    session = SessionLocal()
    role = session.get(Role, role_id)
    session.close()
    return role


def get_role_by_slug(slug: str) -> Optional[Role]:
    """Получение роли по slug"""
    session = SessionLocal()
    role = session.query(Role).filter(Role.slug == slug).first()
    session.close()
    return role


# Функции для работы с задачами
def create_task(
        creator_id: int,
        name: str,
        description: str,
        priority: int,
        grade: float,
        story_points: float,
        color: str = "#000000",
        parent_task_id: Optional[int] = None,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        paused_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None
) -> Task:
    """Создание новой задачи"""
    session = SessionLocal()

    try:
        task = Task(
            creator_id=creator_id,
            parent_task_id=parent_task_id,
            color=color,
            name=name,
            description=description,
            priority=priority,
            grade=grade,
            story_points=story_points,
            started_at=started_at,
            ended_at=ended_at,
            paused_at=paused_at,
            finished_at=finished_at
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


def get_subtasks(parent_task_id: int) -> List[Task]:
    """Получение всех подзадач родительской задачи"""
    session = SessionLocal()
    tasks = session.query(Task).filter(Task.parent_task_id == parent_task_id).all()
    session.close()
    return tasks


def update_task_status(
        task_id: int,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        paused_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None
) -> Optional[Task]:
    """Обновление статусов задачи"""
    session = SessionLocal()

    try:
        task = session.get(Task, task_id)
        if not task:
            return None

        if started_at is not None:
            task.started_at = started_at
        if ended_at is not None:
            task.ended_at = ended_at
        if paused_at is not None:
            task.paused_at = paused_at
        if finished_at is not None:
            task.finished_at = finished_at

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
        name: str,
        slug: Optional[str] = None
) -> TaskRole:
    """Создание новой роли для задачи"""
    session = SessionLocal()

    try:
        # Если slug не указан, генерируем его из name
        if slug is None:
            slug = name.lower().replace(' ', '_')

        task_role = TaskRole(
            task_id=task_id,
            name=name,
            slug=slug
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
    #print("Все таблицы удалены")


def recreate_database():
    """Пересоздание всей базы данных"""
    drop_all_tables()
    init_db()
    add_initial_roles()
    #print("База данных пересоздана")


# Пример использования
if __name__ == '__main__':
    # Инициализация базы данных
    init_db()

    # Добавление начальных ролей
    add_initial_roles()

    # Создание тестового пользователя
    test_user = get_user_by_id(1)
    if test_user is None:
        test_user = add_user(
            slug="test_user",
            email="test@example.com",
            name="Иван",
            surname="Иванов",
            password="hashed_password_here",
            role_id=3  # Разработчик
        )

    if test_user:
        pass
        #print(f"Создан пользователь: {test_user}")

    # Создание тестовой задачи
    if test_user:
        test_task = create_task(
            creator_id=test_user.id,
            name="Первая задача",
            description="Описание первой задачи",
            priority=1,
            grade=5.0,
            story_points=3.0,
            color="#FF0000"
        )

        if test_task:
            #print(f"Создана задача: {test_task}")

            # Создание роли для задачи
            task_role = create_task_role(
                task_id=test_task.id,
                name="Ответственный",
                slug="responsible"
            )

            if task_role:
                #print(f"Создана роль для задачи: {task_role}")

                # Добавление разрешения к роли
                permission = add_permission_to_task_role(
                    task_role_id=task_role.id,
                    name="Редактирование задачи",
                    permission="task.edit"
                )

                #print(f"Добавлено разрешение: {permission}")

                # Назначение пользователя на роль в задаче
                assignment = assign_user_to_task_role(
                    user_id=test_user.id,
                    task_id=test_task.id,
                    task_role_id=task_role.id
                )

                #print(f"Пользователь назначен на роль: {assignment}")

    # Получение пользователя по email
    user_by_email = get_user_by_email("test@example.com")
    if user_by_email:
        pass
        #print(f"Найден пользователь по email: {user_by_email}")

    # Получение всех пользователей
    all_users = get_all_users()
    #print(f"Всего пользователей: {len(all_users)}")

    # Получение всех ролей
    session = SessionLocal()
    all_roles = session.query(Role).all()
    #print(f"Всего ролей в системе: {len(all_roles)}")
    for role in all_roles:
        pass
        #print(f"  - {role}")
    session.close()
