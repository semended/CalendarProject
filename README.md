# CalendarProject

HSSE 25-26, учебный проект — веб-приложение для управления задачами/проектами.

Бэкенд на **FastAPI** + **SQLAlchemy** + **PostgreSQL**, фронт пока рендерится на Jinja-шаблонах.

## Быстрый старт

### 1. Postgres

Поставить и запустить локальный Postgres, создать базу `testdb`:

```bash
# macOS (homebrew)
brew install postgresql@15
brew services start postgresql@15
createdb testdb
# Создать суперпользователя postgres с паролем 123 (если его нет)
psql testdb -c "CREATE USER postgres WITH SUPERUSER PASSWORD '123';"
```

Если хочешь другой DSN — пропиши его в `.env` (см. ниже).

### 2. Виртуальное окружение и зависимости

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Конфиг

```bash
cp .env.example .env
# отредактируй SECRET_KEY на что-нибудь случайное
```

### 4. Инициализация схемы

```bash
alembic upgrade head
```

Все изменения схемы ведутся через Alembic (директория `alembic/versions/`). Новую
миграцию сгенерировать так:

```bash
alembic revision --autogenerate -m "описание изменения"
alembic upgrade head
```

### 5. Запуск

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

Открыть `http://127.0.0.1:8080/`.

## Структура

```
app/
  main.py          — FastAPI app, middleware, роутеры
  config.py        — переменные из .env (DATABASE_URL, SECRET_KEY, CSRF_ENFORCE)
  database.py      — async SQLAlchemy engine + AsyncSession + get_db
  models.py        — ORM-модели (User, Task, TaskRole, TaskRolePermission,
                      TaskUserRole, AvailabilitySlot, TaskEvent, TaskComment, Notification)
  crud.py          — низкоуровневые CRUD-операции (раздел используется сервисами)
  services/        — бизнес-логика (auth_service, task_service, user_service,
                      roles_service, events_service); единая точка для Jinja и /api/v1
  csrf.py          — CSRFMiddleware (включается флагом CSRF_ENFORCE)
  permissions.py   — RBAC, has_permission с наследованием по дереву
  security.py      — bcrypt-хеширование паролей (с fallback на legacy plaintext)
  deps.py          — get_current_user (cookie) / get_current_user_api (cookie+JWT)
  jwt_auth.py      — выпуск/декодирование Bearer-токенов
  templating.py    — Jinja2Templates с Flask-совместимым url_for + csrf_token()
  routers/
    auth.py        — / (start), /registration, /logout, password reset
    tasks.py       — /main, /create_task, /task/{id}, /task_management/{id}, /roles
    users.py       — /user/settings, /user/{id}, /user/{id}/schedule
    api/{auth,tasks,users,roles}.py — JSON под /api/v1
templates/         — Jinja-шаблоны (включая _csrf.html макрос)
static/            — CSS и загружаемые аватарки
```

## Миграция с Flask

Ветка `feat/migrate-to-fastapi` переносит прежний Flask-код (`server.py` + `db_requests.py`) на FastAPI. Важные отличия:

- Пароли теперь хешируются (`bcrypt`). Старые аккаунты с плейнтекстовыми паролями автоматически ре-хешируются при успешном логине.
- `SECRET_KEY` берётся из `.env` — после миграции пользователи один раз разлогинятся, это норм.
- Сессии через `starlette.middleware.sessions` вместо `flask_login`.
- Все `url_for` в шаблонах продолжают работать благодаря compat-шиму (`app/templating.py`).

## REST API

Рядом с Jinja-страницами живёт JSON API под `/api/v1/*` со схемами Pydantic:

- `POST /api/v1/auth/register` — регистрация (JSON body)
- `POST /api/v1/auth/login` — логин (ставит ту же session cookie)
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/token` — OAuth2 password grant → Bearer JWT (form-data)
- `GET  /api/v1/auth/me`, `GET /api/v1/users/me`
- `GET  /api/v1/users/{id}` — публичный профиль с учётом privacy
- `GET  /api/v1/tasks` — задачи текущего юзера
- `POST /api/v1/tasks` — создать задачу/подзадачу
- `GET  /api/v1/tasks/{id}`, `PATCH /api/v1/tasks/{id}`
- `GET  /api/v1/tasks/{id}/subtasks`
- `GET  /api/v1/tasks/{id}/roles` — все роли проекта (системные + кастомные)
- `POST /api/v1/tasks/{id}/roles` — создать кастомную роль с произвольным набором прав
- `PATCH /api/v1/roles/{id}` — менять имя/набор прав (системные роли — только права)
- `DELETE /api/v1/roles/{id}` — удалить кастомную роль (системные защищены 409)
- `GET  /api/v1/permissions` — справочник кодов прав (для UI с чекбоксами)

Аутентификация: cookie-сессия (та же, что у Jinja) **или** `Authorization: Bearer <jwt>` —
JWT берёт приоритет. Для неавторизованных API отдаёт `401 JSON`. JWT на HTML-страницах
игнорируется (HTML смотрит только на cookie).

### CSRF

HTML-формы под cookie-сессиями защищены CSRF-токеном; включается флагом `CSRF_ENFORCE=1`
(по умолчанию off для разработки/тестов). `/api/v1/*` и любой запрос с
`Authorization: Bearer ...` пропускаются. Шаблон вставляет токен макросом
`{% include '_csrf.html' %}`.

Интерактивная документация:

- Swagger UI: <http://127.0.0.1:8080/docs>
- ReDoc: <http://127.0.0.1:8080/redoc>

## Тесты и линтер

```bash
pytest                  # все тесты (нужен Postgres; testdb_test поднимется автоматически)
pytest -k parity        # только parity между Jinja и /api/v1
pytest -k csrf          # CSRF-сценарии (форсит CSRF_ENFORCE=1 через monkeypatch)

ruff check app/         # линт (без конфига — дефолтные правила)
```

Тесты ходят в **реальный** Postgres (`testdb_test`) — фикстуры в `tests/conftest.py`
поднимают БД, прогоняют `alembic upgrade head` и делают TRUNCATE между тестами.

## Демо-данные

```bash
python -m scripts.seed_demo
```

Создаёт пользователя `demo@demo.ru` / пароль `demo` с 7 проектами и 84 слотами
занятости. Один из проектов — **«✦ Запуск нового продукта (демо Гант)»** —
собран специально под показ диаграммы Ганта (4 параллельных трека, иерархия,
смешанные статусы, линия «сегодня»).

## TODO

Текущие оставшиеся задачки проекта — см. `TODO.md`.
