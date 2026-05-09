# КОНТЕКСТ

CalendarProject — учебный (HSSE 25-26) веб-таск-менеджер: проекты с подзадачами, команда с RBAC per-задача, availability-слоты, профиль с privacy. Бэк FastAPI + async SQLAlchemy + Postgres, фронт Jinja SSR + ванильный JS. Текущая рабочая ветка — `feat/calendar-view` (FullCalendar + drag-n-drop). Базовая ветка для всех PR в этом репо — `feat/migrate-to-fastapi` (на ней закрыта вся семестровая программа). Upstream: `vova2007mayorov/CalendarProject`, форк: `semended/CalendarProject`.

# ВАЖНЫЕ ПРАВИЛА

- **НЕ сносить `templates/`** — поддержка двух UI-слоёв (Jinja-страницы + JSON-API под `/api/v1`) это командное архитектурное решение. Возможный отказ от Jinja в пользу чистого JSON-API принимается командой отдельно, не в рамках текущей задачи.
- **НЕ мокать БД в тестах** — используется реальный Postgres через фикстуры в `tests/conftest.py` с TRUNCATE между тестами. Моковые тесты маскируют расхождения с реальной схемой.
- **НЕ коммитить**: `.claude/`, `presentation.pdf`, `.env`, `claude.local.md`, `CLAUDE.local.md`, любые `*.local.*`.
- **Alembic — единственный источник схемы.** Старый `init_db()` хак с `ALTER TABLE … IF NOT EXISTS` удалён. Изменение схемы = новая миграция в `alembic/versions/`.
- **В async permissions ОБЯЗАТЕЛЬНО** `selectinload(TaskUserRole.task_role).selectinload(TaskRole.permissions)` (см. `app/permissions.py:47`). Без него — `MissingGreenlet` в рантайме.
- В Pydantic v2 PATCH-схемах `Optional[X]` не различает "не задано" и "null". Для частичных апдейтов смотри `payload.model_fields_set` (см. `app/routers/api/tasks.py` для PATCH ended_at как референс).
- Идентификаторы — английские, доковые комментарии и UI-строки — русские.
- Комментарии объясняют **почему** (хидденый констрейнт, неочевидный workaround, ссылка на инцидент). Не пишем "что делает код" — это видно из кода.
- В `Task` нет `start_date`. Дедлайн = `ended_at`, начало = `created_at`. `duration` — legacy.
- Модели тянут `func.now()` server-side: при апдейте дедлайна руками пересчитываем `duration` (см. `crud.update_task_deadline`).

# СТЕК

Python 3.13. FastAPI 0.115.5 + Uvicorn 0.32. SQLAlchemy 2.0.36 **async** (asyncpg 0.30, NullPool в тестах). Alembic 1.18. Pydantic 2.10 (+ email). Jinja2 3.1 + ванильный JS. FullCalendar.io 6.1 через CDN. Starlette `SessionMiddleware` (cookie-auth, itsdangerous) + опциональный PyJWT 2.12 Bearer. passlib[bcrypt] 1.7. pytest 8.3 + httpx 0.28 + TestClient. ruff (без конфига — дефолт).

# СТРУКТУРА

```
app/
  main.py            — FastAPI app, middleware, include_router
  config.py          — переменные из .env (DATABASE_URL auto-swap → asyncpg)
  database.py        — async engine, AsyncSession, get_db dependency
  models.py          — User, Task, TaskRole, TaskRolePermission, TaskUserRole, AvailabilitySlot
  schemas.py         — Pydantic v2 (UserPublic/UserMe, TaskCreate/Update/Response, ...)
  crud.py            — top-level async CRUD-функции (без классов Repository)
  deps.py            — get_current_user (Jinja, redirect), get_current_user_api (cookie+JWT), RedirectToLogin
  permissions.py     — RBAC: P_VIEW/P_EDIT_SETTINGS/..., has_permission с наследованием по дереву
  visibility.py      — privacy-фильтр публичного профиля (5 полей × public/authed/self)
  availability.py    — availability-слоты + render_week/render_month
  security.py        — bcrypt + legacy plaintext fallback при логине
  jwt_auth.py        — create_access_token / decode_access_token (PyJWT)
  email.py, tokens.py — verify-email и password-reset токены
  templating.py      — Jinja2Templates с Flask-совместимым url_for + csrf_token()
  csrf.py            — CSRFMiddleware (env CSRF_ENFORCE=1; пропускает /api/v1/* и Bearer)
  services/          — бизнес-логика: auth_service / task_service / user_service /
                       roles_service / events_service. Единый слой для пары роутеров.
  routers/
    auth.py, tasks.py, users.py            — Jinja-страницы (HTMLResponse / TemplateResponse)
    api/{auth,tasks,users,roles}.py        — JSON под /api/v1 (response_model=...)
templates/           — Jinja-шаблоны + partials (_icons.html, _user_menu.html,
                       sidebar.html, _csrf.html)
tests/conftest.py    — реальный Postgres, NullPool, two URLs (async + sync), TRUNCATE-фикстура
alembic/versions/    — миграции: 85155a07e605 (baseline) → a1b2c3d4e5f6 (этап 3:
                       last_login_at/task_events/task_comments/notifications)
                       → b2c3d4e5f6a7 (TaskRole.is_system + бэкфилл)
```

# КОМАНДЫ

```bash
# venv должен быть активирован (см. README: source .venv/bin/activate)

# запуск
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080

# тесты (нужен локальный Postgres; базу testdb_test фикстура создаст сама)
pytest
pytest -k "calendar or drag_drop"      # точечно

# миграции
alembic upgrade head
alembic revision --autogenerate -m "что меняем"

# линт
ruff check app/
```

# АРХИТЕКТУРНЫЕ РЕШЕНИЯ (что и почему)

- **Сервисный слой `app/services/`** — единая точка бизнес-логики. Пары роутеров
  (Jinja vs `/api/v1`) идут в один и тот же сервис, чтобы поведение не дрифтило.
  Сервисы поднимают типизированные исключения (`AuthError`, `TaskServiceError`,
  `RolesServiceError`); роутеры транслируют их в HTTP / TemplateResponse.
- **Двойная авторизация в `deps.get_current_user_api`**: сначала пробуем `Authorization: Bearer …`, если нет — падаем на cookie-сессию. Цель — Swagger UI и Jinja-юзеры через те же `/api/v1/*` без двух копий каждого роута. JWT на HTML-страницах **игнорируется** (HTML-зависимости смотрят только на cookie).
- **CSRF-защита HTML-форм** — `app/csrf.py` + middleware. Включается env-флагом `CSRF_ENFORCE=1` (по умолчанию off для тестов и dev-локалки). Пропускает `/api/v1/*` и любой запрос с `Authorization: Bearer`. Body читается middleware'ом и проигрывается обратно через `_receive`, чтобы downstream роуты увидели нетронутый запрос. Шаблоны вставляют `{% include '_csrf.html' %}` в каждой mutating-форме.
- **Кастомные роли проекта** — `TaskRole.is_system`. Системные (Тимлид/Менеджер/Разработчик) создаются автоматически в `crud.create_task_bundle` с `is_system=True`; бэкфилл существующих делается миграцией `b2c3d4e5f6a7` по имени. Системные нельзя удалить/переименовать (`SystemRoleProtected`), но набор прав менять можно. Кастомные роли создаются через сервис `roles_service.create_custom_role`.
- **События и уведомления** — `task_events` (создание / смена статуса / assign / редактирование) и `notifications` (assign на задачу) пишутся из `events_service`, который дёргается из `task_service`. UI пока не читает эти таблицы, но структура есть.
- **Гибрид Jinja + JSON-API** — Jinja-страницы для end-users, `/api/v1/*` для API-клиентов, общая cookie-авторизация. Документация по этапам миграции в `migration_plan/` upstream рассматривает вариант полного отказа от `templates/`; команда выбрала путь сосуществования двух UI-слоёв.
- **Permissions с наследованием по дереву задач**: если у юзера нет роли на конкретной таске — `permissions.has_permission` поднимается по `parent_task_id` до корня. Роли по подзадачам не дублируются.
- **Тесты на настоящей Postgres**: фикстура `_db_schema` (session-scoped) поднимает `testdb_test` и гонит `alembic upgrade head`. `_clean_tables` (autouse, function-scoped) делает `TRUNCATE … RESTART IDENTITY CASCADE` после каждого теста.
- **NullPool в тестах**: TestClient крутит ASGI в свежем event loop на каждый request, asyncpg-пул из старого loop'а становится невалидным. `conftest.py` подменяет engine на `NullPool` — каждый запрос берёт свежее соединение.

# ИЗВЕСТНЫЕ ГРАББЛИ

- `Task.duration` (BigInteger секунд) — legacy от Flask-схемы, дублирует `ended_at`. Смена дедлайна должна сопровождаться пересчётом этого поля (см. `crud.update_task_deadline`).
- Нет `start_date` у задачи — только `created_at` и `ended_at`. Всплывёт при гантт/недельных вью.
- `Task.status` — computed `@property` (completed/paused/overdue/active), не колонка. Фильтр по статусу = python-side, на больших объёмах будет медленно.
- В Pydantic v2 `Optional` не различает "не задано" vs "null" → используем `payload.model_fields_set` для частичных PATCH.
- `DATABASE_URL` в `.env` жёсткий (`postgres:123@localhost/testdb`) — норм для учебки, блокер для prod.
- Поле `Task.color` — `Text NOT NULL` без дефолта в БД, дефолт только в `TaskCreate` Pydantic (`#0ea5e9`). Создание задачи мимо API схемы пройдёт мимо дефолта.
- `created_at`/`ended_at` хранятся как **naive** datetime. tz-aware payloads нормализуются через `_naive(dt)` в роутерах. Не записывать tz-aware напрямую.
- **`expire_on_commit=False`** в `SessionLocal` (см. `app/database.py`) сохраняет in-memory state ORM-объектов после `commit()`. Если изменили коллекцию через прямой SQL DELETE/INSERT и хотите перечитать — делайте `db.expire(obj, ["relname"])` явно, иначе вернётся stale-данные из identity map'а (см. `roles_service.update_role` для рабочего примера).
- **CSRF-middleware читает body**, поэтому FastAPI Form() во вьюхе ниже сломается, если не проиграть body через `_receive` — это уже сделано в `app/csrf.py`, но если будете править middleware-цепочку — учтите.

# PR-ФЛОУ

- Upstream: `vova2007mayorov/CalendarProject`. Папка `migration_plan/` в upstream содержит документацию по этапам миграции Flask → FastAPI.
- Базовая ветка для PR: **`feat/migrate-to-fastapi`** (не `main` upstream — там ещё старый Flask-код, который заменяет миграция).
- Каждая фича = отдельная ветка от `feat/migrate-to-fastapi` + отдельный PR.
