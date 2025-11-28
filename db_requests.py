# 1. Установить PostgreSQL и поднять его сервис
# 2. Подтянуть все нужные пакеты для исполнения скрипта
# 3. Выполнить команду: createdb testdb
# 4. Запустить скрипт

from sqlalchemy import create_engine, Column, BigInteger, String, Boolean, DateTime, func, select
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "postgresql+psycopg2://postgres:123@localhost:5432/testdb"

engine = create_engine(DATABASE_URL, echo=True)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

class Role(Base):
    __tablename__ = "roles"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    slug = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)

class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    slug = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    surname = Column(String(255), nullable=False)
    patronymic = Column(String(255))
    password = Column(String(255), nullable=False)
    role_id = Column(BigInteger, nullable=False, default=1)
    avatar_url = Column(String(255), nullable=False, default="")
    organization = Column(Boolean, nullable=False, default=False)
    confirmed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

def add_role(slug: str, name: str):
    session = SessionLocal()
    role = Role(slug=slug, name=name)
    session.add(role)
    session.commit()
    session.close()
    #print(f"Added role {slug} with name {name}")

def add_user(user_dict):
    session = SessionLocal()
    user = User(
        slug=user_dict['slug'], # unique slug
        name=user_dict['name'],
        surname=user_dict['surname'],
        patronymic=user_dict['patronymic'],
        password=user_dict['password'],
        role_id=1,
        avatar_url="",
        organization=False,
        confirmed=False
    )
    session.add(user)
    session.commit()
    session.close()
    #print(f"User {id} added.")

def get_user_by_id(user_id: int):
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


if __name__ == '__main__':
    # Создаем таблицы, если они не существуют
    Base.metadata.create_all(engine)
