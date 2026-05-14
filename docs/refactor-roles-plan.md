# Задача для Codex: рефакторинг ролевой модели (3 шага)

## Контекст проекта

Проект CalendarProject — учебный веб-таск-менеджер на FastAPI 0.115 + SQLAlchemy 2.0 async (asyncpg) + Alembic + Pydantic v2 + Jinja2. Рабочая ветка — `feat/migration-cleanup`, базовая ветка для PR — `feat/migrate-to-fastapi`.

В таблице `task_roles` (модель `app/models.py:TaskRole`) хранятся роли проекта со столбцами `id`, `task_id` (FK на `tasks`), `name`, `is_system`. Права привязаны через `task_role_permissions`, назначения юзеров — через `task_user_roles(user_id, task_id, task_role_id)`. Проверка прав идёт через walk вверх по `tasks.parent_task_id` в `app/permissions.py:has_permission`.

## Проблемы, которые надо устранить

1. **`task_service.add_member` не валидирует `role_id`** — через прямой API-вызов `POST /api/v1/tasks/<X>/members` можно прицепить роль из совсем другого дерева задач. Не публичная дыра (требует `manage_members` на проекте-жертве), но нарушение инварианта.

2. **Системные роли клонируются в каждую подзадачу.** `crud.create_task_bundle` вызывается при создании любой задачи, включая подзадачи (см. `app/services/task_service.py:121`), и для каждой создаёт три новые `TaskRole(name=Тимлид/Менеджер/Разработчик, is_system=true)`. В итоге «Тимлид Сайта» и «Тимлид Фронта» — две разные строки. Редактирование прав на корне не влияет на подзадачи.

3. **Кастомная роль видна только на «родной» задаче.** `roles_service.list_roles` фильтрует строго по `TaskRole.task_id == task_id`. На странице подзадачи в дропдауне «добавить участника» кастомные роли с корня не появляются.

Цель: убрать дубликаты системных ролей (одна строка на дерево), сделать наследование единообразным (walk вверх и в правах, и в UI), валидировать роли по дереву.

---

## Порядок реализации

Три коммита подряд, каждый зелёный по тестам, чтобы можно было откатывать поэтапно.

### Коммит 1: Валидация роли по дереву в `add_member`

**Файлы:**
- `app/services/task_service.py` — `add_member` (строки 277-293) + новый helper.
- `app/services/task_service.py` — новая константа исключения `InvalidRoleForTask` рядом с `PermissionDenied`/`InvalidAssignee` (по существующему стилю исключений сервиса).
- `app/routers/tasks.py:404-425` — Jinja POST `/task_management/{task_id}`: поймать новое исключение, показать ошибку через flash/template.
- `app/routers/api/roles.py` или другой API-роутер, если там есть POST члена через API — добавить трансляцию в HTTP 422 (выяснить при правке).

**Логика:**

Новый helper `_role_belongs_to_tree(db, task_id, role_id) -> bool` поднимается по `parent_task_id` и ищет совпадение с `TaskRole.task_id`. Использует тот же паттерн walk-up, что и `permissions.has_permission`.

```python
async def _role_belongs_to_tree(db, task_id, role_id) -> bool:
    role = await db.get(TaskRole, role_id)
    if role is None:
        return False
    cur = task_id
    while cur is not None:
        if cur == role.task_id:
            return True
        task = await db.get(Task, cur)
        if task is None:
            return False
        cur = task.parent_task_id
    return False
```

В `add_member` после проверки `P_MANAGE_MEMBERS` и до `assign_user_to_task_role` добавить:
```python
if not await _role_belongs_to_tree(db, task_id, role_id):
    raise InvalidRoleForTask("Эта роль не принадлежит проекту")
```

**Тесты:**
- POST `/api/v1/tasks/{taskA}/members` (или эквивалентный путь добавления члена) с `role_id` от роли проекта B → 422 / 400.
- POST с валидной ролью того же дерева (включая роль предка) → успех.
- Существующие тесты в `tests/test_custom_roles.py:test_assign_user_to_custom_role` должны остаться зелёными.

**Сложность:** ~30 минут.

---

### Коммит 2: `list_roles` поднимается по дереву

**Файлы:**
- `app/services/roles_service.py:48-56` — `list_roles` переписать на walk-up.
- `templates/task_management.html:54-75` — пометить унаследованные роли в дропдауне (например, «QA (из проекта Сайт)» — определить по `role.task_id != current_task_id`).
- `app/routers/tasks.py:374` — `roles_view` уже строится здесь, добавить флаг `is_inherited` и/или имя родительского проекта в dict для шаблона.
- `app/routers/api/roles.py:37-46` — API endpoint `GET /api/v1/tasks/{task_id}/roles` автоматически вернёт унаследованные роли через тот же `list_roles`. В response schema можно либо ничего не менять (клиент сам вычислит из `task_id`), либо добавить опциональный `is_inherited: bool`.

**Логика `list_roles`:**

Идти от `task_id` вверх по `parent_task_id`, на каждом уровне собирать `TaskRole`-строки этого уровня. Сортировка внутри уровня — как сейчас (`is_system.desc(), id`). Между уровнями — сначала собственные роли задачи, потом унаследованные от предков.

```python
async def list_roles(db, task_id):
    roles = []
    cur = task_id
    while cur is not None:
        result = await db.execute(
            select(TaskRole)
            .options(selectinload(TaskRole.permissions))
            .where(TaskRole.task_id == cur)
            .order_by(TaskRole.is_system.desc(), TaskRole.id)
        )
        roles.extend(result.scalars().all())
        task = await db.get(Task, cur)
        if task is None:
            break
        cur = task.parent_task_id
    return roles
```

**Edge case:** этот коммит **самостоятельно** добавит в дропдаун подзадачи и «Тимлид Фронта», и «Тимлид Сайта» (две одноимённые из-за текущего клонирования). Это будет визуальный шум **до коммита 3**, после которого дубликаты исчезнут. Считаю приемлемым между коммитами; усложнять дедупликацией не нужно.

**Тесты:**
- Создать подзадачу, вызвать `list_roles(subtask_id)` → результат включает кастомную роль с корня.
- `GET /api/v1/tasks/{subtask}/roles` возвращает роли предка.
- Smoke-тест в `tests/test_html_smoke.py:85-86` проверить, что на странице подзадачи всё ещё видны три системных имени.

**Сложность:** ~1 час.

---

### Коммит 3: Перестать клонировать системные роли в подзадачи + миграция

**Файлы:**
- `app/crud.py:129-151` — `create_task_bundle`: ветка `parent_task_id is not None` теперь не создаёт роли, а находит корневую «Тимлид» и назначает создателя на неё.
- `app/crud.py` — новый helper (или inline-запрос) для поиска корневой системной роли по имени.
- **Новая миграция `alembic/versions/<hex>_drop_subtask_system_roles.py`** — data-only, по паттерну `b2c3d4e5f6a7_etap2_custom_roles_is_system.py` и `c3d4e5f6a7b8_merge_subtask_perms.py`. `down_revision` — последняя примененная (`d4e5f6a7b8c9`, посмотреть `alembic/versions/` и поставить актуальный).

**Изменение `create_task_bundle`:**

```python
if parent_task_id is None:
    # Корень — как сейчас: три системные роли, создатель = Тимлид
    teamlead = await create_task_role(db, task.id, "Тимлид", is_system=True)
    manager = await create_task_role(db, task.id, "Менеджер", is_system=True)
    dev = await create_task_role(db, task.id, "Разработчик", is_system=True)
    for role in (teamlead, manager, dev):
        await ensure_role_permissions(db, role)
    await assign_user_to_task_role(db, creator_id, task.id, teamlead.id)
else:
    # Подзадача — переиспользуем системные роли корня
    root = await get_root_task(db, parent_task_id)
    result = await db.execute(
        select(TaskRole).where(
            TaskRole.task_id == root.id,
            TaskRole.is_system.is_(True),
            TaskRole.name == "Тимлид",
        )
    )
    teamlead = result.scalar_one()
    await assign_user_to_task_role(db, creator_id, task.id, teamlead.id)
```

`get_root_task` уже есть в `app/crud.py:154`, переиспользовать.

**Миграция (data-only):**

Алгоритм:
1. Найти все `task_roles`-строки с `is_system=true` и `task_id` НЕ корень (соответствующая `tasks.parent_task_id IS NOT NULL`).
2. Для каждой такой роли найти на её корне роль с тем же `name` и `is_system=true`.
3. Обновить все `task_user_roles.task_role_id` со старой на новую.
4. Удалить связанные `task_role_permissions` старой роли.
5. Удалить саму старую `task_roles`-строку.

Реализовать через `WITH RECURSIVE` CTE для нахождения корня дерева:

```sql
WITH RECURSIVE task_tree AS (
    SELECT id, parent_task_id, id AS root_id
    FROM tasks WHERE parent_task_id IS NULL
    UNION ALL
    SELECT t.id, t.parent_task_id, tt.root_id
    FROM tasks t JOIN task_tree tt ON t.parent_task_id = tt.id
),
roles_to_merge AS (
    SELECT tr.id AS old_id, tr_root.id AS new_id
    FROM task_roles tr
    JOIN task_tree tt ON tr.task_id = tt.id AND tt.id != tt.root_id
    JOIN task_roles tr_root
      ON tr_root.task_id = tt.root_id
     AND tr_root.name = tr.name
     AND tr_root.is_system = true
    WHERE tr.is_system = true
)
UPDATE task_user_roles tur
SET task_role_id = rtm.new_id
FROM roles_to_merge rtm
WHERE tur.task_role_id = rtm.old_id;
```

Затем `DELETE FROM task_role_permissions WHERE task_role_id IN (SELECT old_id ...)` и `DELETE FROM task_roles WHERE id IN (SELECT old_id ...)`. Все через `op.execute(...)`.

**Downgrade** — односторонний (восстановить клоны нельзя без журнала). Документировать в docstring миграции, по аналогии с `c3d4e5f6a7b8_merge_subtask_perms.py:downgrade`.

**Тесты:**
- Проверить `tests/test_events_and_login.py:130` — там `SELECT id FROM task_roles WHERE task_id=parent_id AND name='Разработчик'`. Если `parent_id` это корень — продолжает работать. Если промежуточный уровень — нужно поменять на корневой `task_id`.
- Новый тест: создать корень → создать подзадачу → `SELECT COUNT(*) FROM task_roles WHERE task_id=subtask_id` = 0; `task_user_roles` создателя на подзадачу = 1 и `role.task_id = корень`.
- Прогнать существующие тесты `test_custom_roles`, `test_parity`, `test_html_smoke`, `test_services_edge_cases`.

**Сложность:** ~полдня с миграцией и тестами.

---

## Критичные файлы для модификации

| Файл | Что меняется |
|------|-------------|
| `app/services/task_service.py` | Helper `_role_belongs_to_tree`, валидация в `add_member`, новое исключение `InvalidRoleForTask` |
| `app/services/roles_service.py` | `list_roles` — walk-up по дереву |
| `app/crud.py` | `create_task_bundle` — branch по `parent_task_id`, переиспользует `get_root_task` |
| `app/routers/tasks.py` | Поймать `InvalidRoleForTask`, обогатить `roles_view` пометкой инхеретанса |
| `app/routers/api/roles.py` | (Опционально) добавить `is_inherited` в response schema |
| `templates/task_management.html` | Пометить унаследованные роли в дропдауне |
| `alembic/versions/<new>_drop_subtask_system_roles.py` | Новая data-миграция |
| `tests/test_custom_roles.py`, `tests/test_services_edge_cases.py`, `tests/test_events_and_login.py`, `tests/test_html_smoke.py` | Обновить ожидания + новые тесты |

## Переиспользуемые функции (НЕ создавать заново)

- `app/permissions.py:has_permission` (строка 57) — паттерн walk-up по `parent_task_id`. Скопировать структуру цикла в `_role_belongs_to_tree` и `list_roles`.
- `app/crud.py:get_root_task` (строка 154) — поднимается до корня. Использовать в `create_task_bundle` для нахождения корневых системных ролей.
- `app/crud.py:assign_user_to_task_role` (строка 367) — без изменений, используется и для корня, и для подзадач.
- `app/services/roles_service.py:_reload_role_with_perms` (строка 59) — паттерн перезагрузки с `selectinload`.

## Важные правила проекта (из CLAUDE.md)

- **Alembic — единственный источник схемы.** Никаких `init_db()`-хаков с `ALTER TABLE IF NOT EXISTS`.
- **НЕ мокать БД в тестах** — используется реальный Postgres через фикстуры в `tests/conftest.py` с TRUNCATE между тестами.
- **В async permissions ОБЯЗАТЕЛЬНО** `selectinload(TaskUserRole.task_role).selectinload(TaskRole.permissions)`. Без него — `MissingGreenlet` в рантайме.
- **`expire_on_commit=False`** в `SessionLocal` — после прямого SQL `DELETE`/`INSERT` коллекции могут быть stale. Если после миграции/правки прав делается reload — нужен явный `db.expire(obj, ["permissions"])`.
- **Идентификаторы — английские, доковые комментарии и UI-строки — русские.**
- **Комментарии объясняют ПОЧЕМУ**, а не «что делает код». Если объяснение не нужно — комментарий не пишем.
- **Не создавать новых файлов**, если можно отредактировать существующий. Исключение — новая миграция и (опционально) новый тестовый файл.

## Верификация

После каждого коммита:

1. `pytest` — все тесты зелёные (после коммита 3 — с обновлёнными ожиданиями).
2. `ruff check app/ tests/` — без ошибок.
3. После коммита 3 — `alembic upgrade head` на тестовой БД, проверить:
   ```sql
   SELECT COUNT(*) FROM task_roles tr
   JOIN tasks t ON t.id = tr.task_id
   WHERE tr.is_system = true AND t.parent_task_id IS NOT NULL;
   -- ожидаем 0
   ```
4. Ручной smoke в браузере:
   - Создать проект → подзадачу → открыть `/task_management/<subtask>`.
   - В дропдауне «Добавить участника» видна и роль «Тимлид» (из корня, с пометкой), и кастомная роль если она была создана.
   - Назначить участника на кастомную роль с корня → проверить `has_permission` в подзадачах.
   - Попытаться через `curl`/`/docs` отправить `role_id` от другого проекта → 422.
5. `python -m scripts.seed_demo` — данные сидируются без падений.

## Команды для запуска

```bash
# Активировать venv
source .venv/bin/activate

# Запуск (для ручной проверки)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080

# Тесты
pytest
pytest -k "custom_roles or parity"

# Миграции
alembic upgrade head
alembic revision -m "drop subtask system roles"   # руками, не autogenerate

# Линт
ruff check app/ tests/
```
