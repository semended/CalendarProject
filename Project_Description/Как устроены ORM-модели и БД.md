# Как устроены ORM-модели и БД

## Краткая суть

В проекте — **PostgreSQL**, к которому мы ходим через **async SQLAlchemy 2.0** + драйвер **asyncpg**. ORM-модели описаны декларативно (`Base` + `Column`'ы) в [app/models.py](../app/models.py). Доступ к БД везде однотипный: получить сессию через `Depends(get_db)`, написать `select()`, await'нуть `db.execute(...)`. Схема БД — это **миграции Alembic**, файл моделей лишь отражает её на стороне Python.

## Зачем ORM (одной фразой)

Чтобы не писать SQL-строки руками и не разруливать вручную «row → объект → row». ORM даёт типизированные объекты, ленивую загрузку связей, миграции и переносимость между БД. Цена — слой абстракции, который иногда генерирует «не тот» SQL.

## Async vs sync

Старый стиль (синхронный): обращение к БД блокирует поток, пока ответ не придёт. Если 100 одновременных пользователей — нужно 100 потоков (или процессов).

Async (наш случай): пока ждём ответ от БД, event loop отдаёт управление другому запросу. Один процесс легко тащит сотни конкурентных операций. **Цена** — весь стек должен быть async: `async def`, `await`, async-драйвер БД, async-ORM.

## Подключение: `app/database.py`

Файл маленький, но именно он формирует контракт работы с БД:

[app/database.py:1-19](../app/database.py#L1-L19):

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from app.config import DATABASE_URL, SQL_ECHO

engine = create_async_engine(DATABASE_URL, echo=SQL_ECHO)
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
Base = declarative_base()


async def get_db():
    async with SessionLocal() as db:
        yield db
```

### Что значит каждая строчка

- **`engine`** — пул соединений с БД. Один на всё приложение, переиспользуется. `echo=SQL_ECHO` — для дебага, печатает каждый SQL в консоль.
- **`SessionLocal`** — фабрика сессий. Каждый вызов `SessionLocal()` создаёт новую `AsyncSession`. Сессия — это «единица работы» (Unit of Work): последовательность операций, заканчивающаяся `commit()` или `rollback()`.
- **`autoflush=False`** — не делать неявный flush перед каждым `select()`. Иначе можно случайно отправить в БД полузаполненный объект.
- **`expire_on_commit=False`** — после `commit()` объекты остаются «живыми». Без этого FastAPI бы постоянно падал, пытаясь сериализовать «expired» объекты после транзакции.
- **`Base = declarative_base()`** — родитель для всех моделей. Унаследоваться от него = зарегистрировать таблицу в метаданных.
- **`get_db()`** — FastAPI dependency. На каждый запрос создаётся **своя** сессия и закрывается после ответа. Принцип «одна сессия — один запрос» убирает кучу проблем с потокобезопасностью.

## Как использовать сессию в роуте

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db

@router.get("/main")
async def main_page(user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    tasks = await crud.get_tasks_by_user_id(db, user.id, roots_only=True)
    return ...
```

`db` живёт ровно столько, сколько обрабатывается запрос. На выходе из роута `async with` сам закрывает сессию.

## Стиль 2.0: `select()` + `execute()`

В SQLAlchemy 1.x был стиль `db.query(Task).filter(...).all()`. В 2.0 — единый паттерн через объекты `Select`:

```python
# из app/crud.py:95-97
async def get_user_by_email(db, email):
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()
```

### Что возвращает `execute()`

Объект `Result`, у которого есть несколько способов извлечь данные:

| Метод | Возвращает |
|---|---|
| `.scalar_one_or_none()` | Один объект или `None` (если 0 строк); ошибка, если строк > 1 |
| `.scalar_one()` | Один объект; ошибка, если строк ≠ 1 |
| `.scalars().first()` | Первый объект из всех найденных или `None` |
| `.scalars().all()` | Список объектов |

Без `.scalars()` ты получишь кортежи (`Row`), а не сами объекты — это приём для запросов с несколькими колонками.

### Простой `db.get(...)` для PK

Для поиска по primary key есть короткий путь:

```python
# из app/crud.py:91-92
async def get_user_by_id(db, user_id):
    return await db.get(User, user_id)
```

Это эквивалентно `select(User).where(User.id == user_id)`, но с identity-map: если объект уже загружен в эту сессию — вернёт его без обращения к БД.

## Декларативные модели

Все таблицы описаны в [app/models.py](../app/models.py) как классы, унаследованные от `Base`. Один `Column` = один столбец. Один `relationship` = одна связь.

### `User` ([app/models.py:11-39](../app/models.py#L11-L39))

```python
class User(Base):
    __tablename__ = "users"
    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    email      = Column(String(255), unique=True, nullable=False)
    name       = Column(String(255), nullable=False)
    password   = Column(String(255), nullable=False)   # bcrypt-хеш
    confirmed  = Column(Boolean, nullable=False, default=False)
    privacy_email = Column(String(16), nullable=False, server_default="self")
    ...
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    created_tasks = relationship("Task", back_populates="creator", foreign_keys="Task.creator_id")
    task_roles    = relationship("TaskUserRole", back_populates="user")
```

Несколько важных деталей:

- **`server_default`** vs **`default`**. `default` — Python-значение, подставляется на стороне ORM. `server_default` — SQL-выражение в `CREATE TABLE`, работает даже при прямой вставке через `psql`.
- **Privacy-поля** (`privacy_email`, `privacy_bio`, ...) — строковый enum со значениями `"self"` и `"authed"`. `"self"` — видно только владельцу, `"authed"` — любому залогиненному.
- **`relationship`** — это уже про ORM, а не про SQL. `created_tasks` не существует в БД, но ORM его подгружает по FK `Task.creator_id`.

### `Task` (self-referential) ([app/models.py:42-76](../app/models.py#L42-L76))

```python
class Task(Base):
    __tablename__ = "tasks"
    id             = Column(BigInteger, primary_key=True)
    parent_task_id = Column(BigInteger, ForeignKey("tasks.id", ondelete="CASCADE"))
    creator_id     = Column(BigInteger, ForeignKey("users.id"))
    ...

    parent_task = relationship("Task", remote_side=[id], back_populates="subtasks")
    subtasks    = relationship("Task", back_populates="parent_task")
```

`remote_side=[id]` — обязательно для self-references: говорит ORM, какая колонка «удалённая» (т. е. `id` родителя), какая «локальная» (`parent_task_id`).

Также интересно: модель определяет вычисляемое свойство `status` ([app/models.py:64-73](../app/models.py#L64-L73)):

```python
@property
def status(self) -> str:
    if self.state == "done":   return "completed"
    if self.state == "paused": return "paused"
    if self.ended_at and self.ended_at < datetime.now():
        return "overdue"
    return "active"
```

Это **не колонка БД**, это просто Python-метод. Хорошее место для производных значений: их не нужно хранить, и они автоматически отражают актуальное состояние.

### Trio для прав ([app/models.py:100-150](../app/models.py#L100-L150))

`TaskRole` → many-to-many → `User` через `TaskUserRole`, плюс `TaskRolePermission` для конкретных прав. Подробно разобрано в [Как устроена система проектов.md](./Как%20устроена%20система%20проектов.md).

### `AvailabilitySlot` ([app/models.py:79-97](../app/models.py#L79-L97))

Свободно/занято расписание пользователя. Используется на странице `/calendar`. `__table_args__` добавляет составной индекс `(user_id, start_at)` — он критичен для скорости запроса «слоты юзера за месяц».

## Relationships: `selectinload` и проблема N+1

Когда у тебя есть `task.user_roles`, ORM по умолчанию **lazy-loads**: при первом обращении делает отдельный SELECT. В цикле это превращается в катастрофу N+1: 1 запрос на список + N запросов на каждый элемент.

В нашем коде уже встречается жадная загрузка через `selectinload` ([app/permissions.py:47](../app/permissions.py#L47)):

```python
result = await db.execute(
    select(TaskUserRole)
    .options(selectinload(TaskUserRole.task_role).selectinload(TaskRole.permissions))
    .where(TaskUserRole.user_id == user_id, TaskUserRole.task_id == task_id)
)
```

`selectinload` догружает связь **одним отдельным запросом** через `WHERE id IN (...)` — это идеально для коллекций. Альтернатива — `joinedload` (через JOIN, лучше для one-to-one).

Если SQL_ECHO включён — ты сразу увидишь эти JOIN'ы и поймёшь, как ORM строит запросы.

## Транзакции и `commit`

Каждая функция в `crud.py` сама делает `await db.commit()` после изменений:

```python
# app/crud.py:38-62
async def update_user(db, user_id, user_dict):
    user = await db.get(User, user_id)
    if not user: return None
    for key, value in user_dict.items():
        setattr(user, key, value)
    await db.commit()
    await db.refresh(user)
    return user
```

`db.refresh(user)` после `commit()` нужен, чтобы перечитать поля, которые могли измениться на стороне БД (например, `updated_at`-триггер).

Если в одной операции хочется атомарно сделать несколько вещей (как в `create_task_bundle`), всё пишут в одну сессию и в конце делают **один** `commit`. У нас, правда, бандл коммитит каждый шаг — это не идеально с точки зрения атомарности, но для учебного проекта приемлемо.

## Миграции через Alembic

**Главное правило**: схема БД создаётся **только** через Alembic. Нельзя `Base.metadata.create_all()`.

### Как это работает

1. Меняешь модель в `app/models.py` (добавил колонку, переименовал поле, ...).
2. Запускаешь `alembic revision --autogenerate -m "add column ..."`.
3. Alembic сравнивает текущие модели с состоянием БД и генерит файл в `alembic/versions/`.
4. Открываешь файл, ПРОСМАТРИВАЕШЬ глазами (autogenerate не идеален), правишь если нужно.
5. `alembic upgrade head` — применяешь миграцию.

### Текущее состояние

Сейчас в проекте **одна миграция** ([alembic/versions/85155a07e605_baseline.py](../alembic/versions/85155a07e605_baseline.py)) — baseline, создающая все таблицы разом. Когда добавишь следующую, файл будет ссылаться на эту через `down_revision`.

### Откат

```bash
alembic downgrade -1   # откатить последнюю миграцию
alembic downgrade base # откатить ВСЁ (опасно)
```

### Почему именно Alembic, а не `create_all`

`create_all()` — это «снимок» текущих моделей. Он не знает истории, не умеет переименовывать колонки (он их удалит и создаст новые, потеряв данные). Alembic фиксирует **переходы** между версиями схемы — это и есть source of truth.

## Тесты и БД

Из [CLAUDE.md](../CLAUDE.md): тесты используют **реальный** Postgres, базу `testdb_test`. Никаких моков — это сознательный выбор: моки часто скрывают баги интеграции с asyncpg или Alembic.

Это, правда, означает, что для запуска тестов нужен живой Postgres локально (`createdb testdb_test`) и применённые миграции.

## Технологии под капотом

### SQLAlchemy 2.0
Стандарт de-facto для Python-ORM. В 2.0 модернизирован API: всё через `select()`, явные `await`, никаких неявных запросов «магией». Основные блоки: **Core** (SQL-builder, без ORM) и **ORM** (объекты + сессии). Мы используем ORM поверх Core.

### asyncpg
Самый быстрый async-драйвер для Postgres. Написан на Cython, не использует libpq, своя реализация протокола. Не совместим с DBAPI — поэтому SQLAlchemy общается с ним через специальный адаптер. Имя в URL — `postgresql+asyncpg://`.

### Declarative ORM
Стиль описания моделей классами (как у нас). Альтернатива — **imperative** (через `Table(...)` отдельно от классов) — выглядит более «низкоуровнево», но тяжелее читать.

### Identity Map
Внутри одной сессии один и тот же объект (по PK) — это **один** Python-объект. То есть `await db.get(User, 1)` дважды вернёт один и тот же `id(...)`. Это упрощает работу с графами объектов: не нужно бояться дубликатов.

### Unit of Work
Паттерн, при котором сессия копит изменения и применяет их одной транзакцией. SQLAlchemy реализует это через `db.add(...)` + `await db.commit()`.

### Alembic
Инструмент миграций для SQLAlchemy. Каждая миграция — Python-файл с двумя функциями: `upgrade()` и `downgrade()`. Внутри — Alembic-операции (`op.add_column(...)`, `op.create_table(...)`), которые транслируются в SQL.

## Что почитать

- [SQLAlchemy 2.0 — Unified Tutorial](https://docs.sqlalchemy.org/en/20/tutorial/) — фундаментальное чтение, без него многое будет непонятно.
- [SQLAlchemy AsyncIO docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) — про async-сессии, `selectinload`, ловушки.
- [asyncpg docs](https://magicstack.github.io/asyncpg/current/) — на случай, если нужны прямые быстрые запросы в обход ORM.
- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html) — как писать миграции и не сломать прод.
- [Alembic Auto Generating Migrations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html) — что autogenerate умеет, что не умеет (важно).
- [PostgreSQL — Official Tutorial](https://www.postgresql.org/docs/current/tutorial.html) — про саму БД полезно понимать.
- [SQLAlchemy 2.0 ORM Quick Start](https://docs.sqlalchemy.org/en/20/orm/quickstart.html) — короткий старт, если документация выше показалась объёмной.
- [Habr — SQLAlchemy 2.0 на практике](https://habr.com/ru/articles/766204/) — обзорная статья на русском.
