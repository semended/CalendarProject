# Calendar-project — контекст для Claude

## 1. CLAUDE.md (правила работы)

**Глобальный `~/.claude/CLAUDE.md`** — только про двухуровневую память (global vs project), формат сохранения (frontmatter + строка в `MEMORY.md`).

**Проектный `CLAUDE.md`** (закоммичен) + `CLAUDE.local.md` (личный, gitignore):

- **Стек:** Python 3.13, FastAPI 0.115 + Uvicorn, **async** SQLAlchemy 2.0 + asyncpg, Alembic, Pydantic v2, Jinja2 + ванильный JS, FullCalendar через CDN, Starlette SessionMiddleware (cookie) + опц. PyJWT, passlib[bcrypt], pytest + httpx + TestClient, ruff (без конфига).
- **Команды:** `uvicorn app.main:app --reload --host 127.0.0.1 --port 8080`, `pytest`, `alembic upgrade head`, `alembic revision --autogenerate -m "..."`, `ruff check app/`. Локально — с префиксом `.venv/bin/` (личная привычка из `CLAUDE.local.md`).
- **Жёсткие НЕ:** не сносить `templates/` (гибрид Jinja + `/api/v1/*` — командное решение), не мокать БД в тестах (реальный Postgres через `tests/conftest.py` + TRUNCATE), не коммитить `.claude/`, `.env`, `*.local.*`, `presentation.pdf`. Alembic — единственный источник схемы.
- **PR-флоу:** базовая ветка для PR — `feat/migrate-to-fastapi` (НЕ main upstream — там старый Flask).

## 2. Память про пользователя (user-level)

- Владислав, HSSE НИУ ВШЭ, 25-26 уч. год. GitHub: `semended`.
- Питон-бэк (Flask → FastAPI), HTML/CSS/Jinja на фронте.
- **Тон:** терсно по-русски, неформально, мат ок.
- **Автономия:** делегировать в subagent'ы (Explore / domain agents), на ближнеравных решениях — выбирать дефолт и идти дальше, спрашивать только на блокерах и необратимых операциях. Саммари короткие — диффы юзер читает сам.

## 3. Project memory (статус)

- **Семестровая программа (5 пунктов) закрыта 2026-04-20** на ветке `feat/migrate-to-fastapi`: Flask→FastAPI, polish, email/reset, RBAC, privacy. Дефолтно считать всё закрытым; новые задачи — вне роадмапы.
- **API-решение (2026-04-19):** гибрид Jinja + `/api/v1/*` с общей cookie-авторизацией. Jinja first-class, API аддитивный.
- **Дизайн (Сколково light cream)** — палитра + Fraunces/Manrope/JetBrains Mono + структурные паттерны (`form-block/form-group/notice/status-chip`), без `<fieldset>/<legend>`. Все шаблоны мигрированы.
- **План «3 фичи»** из `CLAUDE.local.md`:
  1. `feat/calendar-view` — был в работе (FullCalendar + drag-n-drop).
  2. `feat/kanban-board` — TODO, без миграций.
  3. `feat/ai-subtask-split` — TODO, нужен `ANTHROPIC_API_KEY`.
- **Текущая ветка** `feat/migration-cleanup`, не та, что в памяти — память на 21 день старая, проверять реальный код.

## 4. Граббли (проектные)

- `Task.duration` (BigInteger секунд) — legacy, дублирует `ended_at`. При смене дедлайна пересчитывать вручную (`crud.update_task_deadline`).
- Нет `Task.start_date` — только `created_at` и `ended_at`. Всплывёт в гантт/неделях.
- `Task.status` — computed `@property`, не колонка. Фильтр python-side.
- Pydantic v2 `Optional` не различает "не задано" vs `null` → использовать `payload.model_fields_set` для PATCH (референс — PATCH `ended_at` в `app/routers/api/tasks.py`).
- `DATABASE_URL` в `.env` жёсткий (`postgres:123@localhost/testdb`).
- `Task.color` — `Text NOT NULL` без БД-дефолта, дефолт `#0ea5e9` только в Pydantic.
- `created_at`/`ended_at` — **naive** datetime. tz-aware нормализовать через `_naive(dt)`.
- `expire_on_commit=False` в `SessionLocal` — после прямого SQL DELETE/INSERT по коллекции делать `db.expire(obj, ["relname"])`, иначе stale из identity map (пример — `roles_service.update_role`).
- CSRF-middleware читает body и проигрывает через `_receive` — править middleware-цепочку аккуратно.
- В async `permissions` **обязательно** `selectinload(TaskUserRole.task_role).selectinload(TaskRole.permissions)` — иначе `MissingGreenlet`.

## 5. Hooks / settings Claude Code

**Проектный `.claude/settings.json`:**

- `allow`: `python*`, `uvicorn*`, `pip install/show/list/freeze`, `pytest*`, `alembic*`, `psql*`, безопасные git-команды (`status`/`diff`/`log`/`show`/`branch`/`switch`/`checkout`/`add`/`commit`/`stash`/`restore`), `gh pr`/`gh issue`/`gh repo view`, `ls`/`tree`/`wc`/`find`, `cat app|templates|static|README.md|TODO.md|requirements.txt`.
- `deny`: чтение/редактирование `.env*`, `rm -rf`, `dropdb`, `psql ... DROP*`, `git push --force`, `git reset --hard`.
- `ask`: `git push:*`, `alembic downgrade:*` (поэтому пуш в форк спрашивает разрешения).

**Глобальный `~/.claude/settings.json`:**

- `defaultMode: bypassPermissions` + `skipDangerousModePermissionPrompt: true`.
- Жёсткий `deny`: `rm -rf` по системным путям, `sudo*`, `dd`, `mkfs*`, `shutdown/reboot`, `chmod -R 777 /*`, `curl|sh`, `eval *`, `git push --force/-f`, `git reset --hard`, `git clean -fd*`, `git checkout .`, `git branch -D *`.
- `ask`: всё с `.env`, секретами, SSH-ключами, `id_rsa*`, `~/.ssh`, `~/.aws`, `~/.kube/config`, `git push*`, `npm publish`, `brew uninstall`, `docker * prune`.
- **Hooks**: `Stop`, `PermissionRequest`, `PreToolUse(AskUserQuestion)` → нодовые нотификаторы в `~/.claude/hooks/claude-notifier-on-{stop,permission,question}.js`. Это **уведомлялки**, не линтеры/форматтеры — на код не влияют.

**Auto-линтеров/форматтеров на хуках нет.** Ruff — вручную или в CI, не pre-commit.

**Subagent'ы в `.claude/agents/`:**

- `db-schema` — Alembic + async SQLAlchemy (Sonnet).
- `fastapi-reviewer` — ⚠️ описание устарело: говорит про **sync** FastAPI/psycopg2/SessionMiddleware, по факту проект async и есть JWT-слой. Ревью оттуда брать с поправкой.
- `jinja-frontend` — шаблоны + статика, без JS-фреймворков.

**Slash-команды:** `/end-session` — пишет лог в `sessions/YYYY-MM-DD.md` (gitignored), на новых проектных грабблях спрашивает добавить ли в `CLAUDE.md → ИЗВЕСТНЫЕ ГРАББЛИ`. Не пушит, не коммитит автоматом.

**MCP** (только инструкции): `context7` — для документации либ/фреймворков/SDK. Использовать когда вопрос про API/синтаксис/конфиг конкретной либы, **не** для рефакторинга/бизнес-логики/code-review.
