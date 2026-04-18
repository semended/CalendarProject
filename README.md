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
python -m app.init_db
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
  config.py        — переменные из .env
  database.py      — SQLAlchemy engine + Session + get_db
  models.py        — ORM-модели (User, Task, TaskRole, TaskRolePermission, TaskUserRole)
  crud.py          — CRUD-операции
  security.py      — bcrypt-хеширование паролей (с fallback на legacy plaintext)
  deps.py          — зависимости FastAPI (get_current_user и пр.)
  templating.py    — Jinja2Templates с Flask-совместимым url_for
  init_db.py       — точка входа для создания таблиц
  routers/
    auth.py        — / (start), /registration, /logout
    tasks.py       — /main, /create_task, /task/{id}, /task_management/{id}
    users.py       — /user/settings, /user/{id}
templates/         — Jinja-шаблоны (те же, что были при Flask)
static/            — CSS и загружаемые аватарки
```

## Миграция с Flask

Ветка `feat/migrate-to-fastapi` переносит прежний Flask-код (`server.py` + `db_requests.py`) на FastAPI. Важные отличия:

- Пароли теперь хешируются (`bcrypt`). Старые аккаунты с плейнтекстовыми паролями автоматически ре-хешируются при успешном логине.
- `SECRET_KEY` берётся из `.env` — после миграции пользователи один раз разлогинятся, это норм.
- Сессии через `starlette.middleware.sessions` вместо `flask_login`.
- Все `url_for` в шаблонах продолжают работать благодаря compat-шиму (`app/templating.py`).

## TODO

Текущие оставшиеся задачки проекта — см. `TODO.md`.
