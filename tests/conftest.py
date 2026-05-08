"""Фикстуры для integration-тестов.

Работает так:
1. Перед любым импортом `app.main` подменяем DATABASE_URL на тестовую БД
   (по умолчанию `testdb_test` рядом с dev-base'ой).
2. Session-scoped фикстура создаёт БД, если её нет, и прогоняет `alembic upgrade head`.
3. Autouse function-scoped фикстура делает TRUNCATE всех таблиц после каждого
   теста — следующий тест всегда стартует с чистой схемы.
4. `client` — fresh TestClient на каждый тест (своя сессия/куки).
"""
import os
import subprocess

_TEST_DB_URL_ASYNC = os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:123@localhost:5432/testdb_test",
)
_TEST_DB_URL_SYNC = (
    _TEST_DB_URL_ASYNC
    .replace("postgresql+asyncpg://", "postgresql://", 1)
    .replace("postgresql+psycopg2://", "postgresql://", 1)
)
_TEST_DB_NAME = _TEST_DB_URL_SYNC.rsplit("/", 1)[-1]
_ADMIN_URL = _TEST_DB_URL_SYNC.rsplit("/", 1)[0] + "/postgres"

import psycopg2
import psycopg2.extensions
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# TestClient прокручивает ASGI-app в свежем event loop на каждый request
# через anyio.portal. Пул asyncpg-коннектов из предыдущего loop'а после
# этого становится невалидным ("another operation is in progress"), поэтому
# подменяем engine на NullPool — каждый запрос берёт свежее соединение.
import app.database as _app_db  # noqa: E402

_app_db.engine = create_async_engine(_TEST_DB_URL_ASYNC, poolclass=NullPool)
_app_db.SessionLocal = async_sessionmaker(
    bind=_app_db.engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

_TRUNCATE_SQL = """
TRUNCATE
  users, tasks, availability_slots,
  task_roles, task_role_permissions, task_user_roles,
  task_events, task_comments, notifications
RESTART IDENTITY CASCADE
"""


def _ensure_test_db() -> None:
    conn = psycopg2.connect(_ADMIN_URL)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (_TEST_DB_NAME,))
    if cur.fetchone() is None:
        cur.execute(f'CREATE DATABASE "{_TEST_DB_NAME}"')
    cur.close()
    conn.close()


def _alembic_upgrade_head() -> None:
    subprocess.run(
        ["alembic", "upgrade", "head"],
        check=True,
        env={**os.environ, "DATABASE_URL": _TEST_DB_URL_ASYNC},
    )


@pytest.fixture(scope="session", autouse=True)
def _db_schema():
    _ensure_test_db()
    _alembic_upgrade_head()
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    conn = psycopg2.connect(_TEST_DB_URL_SYNC)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(_TRUNCATE_SQL)
    conn.close()


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)
