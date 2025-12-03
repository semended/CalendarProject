# 1. Установить PostgreSQL и поднять его сервис
# 2. Подтянуть все нужные пакеты для исполнения скрипта
# 3. Выполнить команду: createdb testdb
# 4. Запустить скрипт

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, func, select
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///database.db"

engine = create_engine(DATABASE_URL, echo=True)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    surname = Column(String(255), nullable=False)
    patronymic = Column(String(255))
    password = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    role_id = Column(Integer, nullable=False, default=1)
    avatar_url = Column(String(255), nullable=False, default="")
    organization = Column(Boolean, nullable=False, default=False)
    confirmed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

# Создаем таблицы, если они не существуют
Base.metadata.create_all(engine)

def add_role(slug: str, name: str):
    session = SessionLocal()
    role = Role(slug=slug, name=name)
    session.add(role)
    session.commit()
    session.close()
    print(f"Added role {slug} with name {name}")

def add_user(slug: str, password: str, name: str, surname: str, patronymic: str = None, email: str = "test@example.com"):
    session = SessionLocal()
    user = User(
        slug=slug, # unique slug
        name=name,
        surname=surname,
        patronymic=patronymic,
        password=password,
        email=email,
        role_id=1,
        avatar_url="",
        organization=False,
        confirmed=False
    )
    session.add(user)
    session.commit()
    user_id = user.id
    session.close()
    print(f"User {user_id} added.")

def get_user(user_id: int):
    session = SessionLocal()
    user = session.get(User, user_id)
    session.close()
    return user

def get_user_by_slug(slug: str):
    session = SessionLocal()
    stmt = select(User).where(User.slug.in_([slug]))
    user = None
    for u in session.scalars(stmt):
        user = u
        break
    session.close()
    return user

def get_role(role_id: int):
    session = SessionLocal()
    role = session.get(Role, role_id)
    session.close()
    return role

if __name__ == "__main__":
    role = get_role(1)
    if role is None:
        add_role("meow", "meow")
    user = get_user_by_slug("user1")
    if user is None:
        add_user("user1", "securepassword", "Ivan", "Ivanov", "Ivanovich")
        user = get_user_by_slug("user1")
    print(user.id, user.slug, user.name, user.surname, user.patronymic, user.password, user.role_id, user.avatar_url, user.organization, user.confirmed, user.created_at)
