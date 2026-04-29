# Как работает REST API

## Краткая суть

Под префиксом `/api/v1/*` живёт JSON-API: те же действия, что доступны через HTML, но без шаблонов и редиректов — на вход JSON, на выход JSON. Это нужно для мобилок, скриптов, тестов и Swagger UI.

Авторизация — через JWT (`Authorization: Bearer ...`) или cookie-сессию (fallback). Валидация входа и формат выхода — через Pydantic-схемы. Документация генерируется FastAPI автоматически и доступна на `/docs` (Swagger UI) и `/redoc` (ReDoc).

## Структура

```
/api/v1/
├── auth/
│   ├── POST   /login        — JSON логин (cookie + UserMe)
│   ├── POST   /register     — регистрация (cookie + UserMe, 201)
│   ├── POST   /logout       — стереть сессию (требует auth)
│   ├── POST   /token        — OAuth2 password flow → JWT
│   └── GET    /me           — текущий юзер (требует auth)
├── users/
│   ├── GET    /me           — alias для /auth/me (зависит от реализации)
│   ├── GET    /{id}         — публичный профиль (privacy-фильтр)
│   └── PATCH  /{id}         — обновление (только своего)
└── tasks/
    ├── GET    /             — мои задачи (limit/offset)
    ├── POST   /             — создать задачу/проект (201)
    ├── GET    /{id}         — одна задача (P_VIEW)
    ├── GET    /{id}/subtasks — подзадачи (P_VIEW)
    └── PATCH  /{id}         — обновить (P_EDIT_SETTINGS)
```

Все сабр-роутеры собираются в один `api_router` ([app/routers/api/__init__.py](../app/routers/api/__init__.py#L1-L8)):

```python
from fastapi import APIRouter
from app.routers.api import auth, tasks, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)    # → /api/v1/auth/*
api_router.include_router(users.router)   # → /api/v1/users/*
api_router.include_router(tasks.router)   # → /api/v1/tasks/*
```

И затем в [app/main.py:27](../app/main.py#L27):

```python
app.include_router(api_router)
```

## Pydantic-схемы

Все «типы данных» API живут в [app/schemas.py](../app/schemas.py). FastAPI использует их для:

1. **Валидации входа** (если payload не подходит — 422 без обращения к роуту).
2. **Сериализации выхода** (`response_model=...` гарантирует, что в JSON попадут только нужные поля).
3. **Генерации OpenAPI** (Swagger UI рисует интерактивные формы).

### Юзеры

[app/schemas.py:9-49](../app/schemas.py#L9-L49):

```python
class UserPublic(BaseModel):
    """Public view of a user, privacy-filtered by the caller before instantiation."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    surname: str
    avatar_url: Optional[str] = None
    email: Optional[str] = None
    bio: Optional[str] = None
    ...

class UserMe(BaseModel):
    """Full self view — caller is always authorised to see everything."""
    ...
    confirmed: bool
    privacy_email: str
    privacy_bio: str
    ...
```

Две схемы для одного `User`:

- **`UserPublic`** — с `Optional[...]` на чувствительных полях. Перед сериализацией роут сам зачищает поля по privacy-настройкам жертвы.
- **`UserMe`** — для эндпоинта «я о себе». Видны все поля, включая privacy-флаги.

`model_config = ConfigDict(from_attributes=True)` (старый `Config: orm_mode = True` в Pydantic 1) — разрешает Pydantic читать атрибуты SQLAlchemy-объекта напрямую, без `dict(...)`.

### Авторизация

[app/schemas.py:54-65](../app/schemas.py#L54-L65):

```python
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=255)
    surname: str = Field(min_length=1, max_length=255)
    patronymic: Optional[str] = Field(default=None, max_length=255)
```

`EmailStr` — встроенный pydantic-тип. Если строка не похожа на email — 422 «field is not a valid email».

### Задачи

[app/schemas.py:69-103](../app/schemas.py#L69-L103):

```python
_TASK_STATE_PATTERN = r"^(todo|in_progress|review|done|paused)$"

class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    color: str = "#0ea5e9"
    ended_at: Optional[datetime] = None
    parent_task_id: Optional[int] = None
    assignee_id: Optional[int] = None

class TaskUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    state: Optional[str] = Field(default=None, pattern=_TASK_STATE_PATTERN)
    ...

class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    state: str       # из БД
    status: str      # из @property Task.status (вычисляемое)
    creator_id: int
    ...
```

В `TaskUpdate` все поля `Optional` — это PATCH (частичное обновление). В `TaskResponse` есть и `state` (чистая колонка), и `status` (свойство Python из `app/models.py`) — Pydantic с `from_attributes=True` спокойно читает оба.

### Прочее

[app/schemas.py:107-113](../app/schemas.py#L107-L113):

```python
class MessageResponse(BaseModel):
    message: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

`TokenResponse` — стандартная форма ответа OAuth2 password flow. Swagger UI её узнает.

## Двойная авторизация (повторно, кратко)

API использует **`get_current_user_api`** ([app/deps.py:45-63](../app/deps.py#L45-L63)) — она пытается:

1. Декодировать JWT из `Authorization: Bearer ...`.
2. Если токена нет — fallback на cookie-сессию.
3. Если ничего нет — `HTTPException(401)`.

Подробнее в файле [Как работает авторизация.md](./Как%20работает%20авторизация.md).

## OAuth2 password flow

Это и есть «откуда брать JWT».

[app/routers/api/auth.py:73-87](../app/routers/api/auth.py#L73-L87):

```python
@router.post("/token", response_model=TokenResponse)
async def api_issue_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await crud.get_user_by_email(db, form_data.username)
    if user is None or not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if not is_hashed(user.password):
        await crud.update_user_password(db, user.id, hash_password(form_data.password))
    return TokenResponse(access_token=encode_access_token(user.id))
```

Особенности:

- `OAuth2PasswordRequestForm` — встроенная зависимость FastAPI: ждёт `application/x-www-form-urlencoded` с полями `username` и `password`. **Не JSON.** Это требование стандарта OAuth2.
- В нашей схеме `username` — это email (мы переиспользуем поле для удобства).
- На выходе — `{"access_token": "...", "token_type": "bearer"}`.

В Swagger UI справа сверху есть кнопка «Authorize» — она открывает форму, и под капотом дёргает именно `/api/v1/auth/token`. После успеха Swagger автоматически добавляет `Authorization: Bearer ...` ко всем запросам.

Параллельно работает обычный `/api/v1/auth/login` ([app/routers/api/auth.py:23-35](../app/routers/api/auth.py#L23-L35)) с JSON-телом — он ставит cookie-сессию и возвращает `UserMe`. Зачем нам два? `/login` удобнее для тестов и web-фронта (cookie сразу подхватывается), `/token` — для мобилок и stateless-клиентов.

## Эндпоинт создания задачи (как пример хорошей структуры)

[app/routers/api/tasks.py:38-73](../app/routers/api/tasks.py#L38-L73):

```python
@router.post("", response_model=TaskResponse, status_code=201)
async def api_create_task(
    payload: TaskCreate,
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    if payload.parent_task_id is not None:
        if not await has_permission(db, user.id, payload.parent_task_id, P_CREATE_SUBTASK):
            raise HTTPException(status_code=403, detail="Нет прав на создание подзадачи")

    ended_at = _naive(payload.ended_at) if payload.ended_at is not None else None
    if ended_at is not None:
        duration = int((ended_at - datetime.now()).total_seconds())
    else:
        duration = 2_147_000_000

    assignee_id = payload.assignee_id
    if assignee_id is not None:
        candidates = await crud.get_assignee_candidates(db, payload.parent_task_id, user.id)
        if not any(c.id == assignee_id for c in candidates):
            raise HTTPException(status_code=422, detail="Этот пользователь не может быть назначен на задачу")

    return await crud.create_task_bundle(db, ...)
```

Поток типичного API-эндпоинта:

1. **Авторизация** (через `Depends(get_current_user_api)`).
2. **Проверка прав** (через `has_permission`) — возвращаем 403, если нельзя.
3. **Бизнес-валидация** (например, что `assignee_id` входит в кандидатов) — возвращаем 422.
4. **Делегирование в `crud`** — никаких прямых SQL-запросов в роуте.
5. **Возврат объекта** — Pydantic сам сериализует в `TaskResponse`.

`status_code=201` — стандарт REST для «создан новый ресурс».

## Различие HTML vs API одной таблицей

| | HTML-роуты | `/api/v1/*` |
|---|---|---|
| Зависимость auth | `get_current_user` | `get_current_user_api` |
| Источник auth | cookie | Bearer-токен → cookie |
| Нет авторизации | `RedirectToLogin` → 303 | `HTTPException(401)` JSON |
| Формат входа | `Form(...)` (multipart) | JSON (`payload: SomeBaseModel`) |
| Формат выхода | `templates.TemplateResponse(...)` | `response_model=...` |
| Бизнес-ошибки | Шаблон с `{"error": "..."}` | `HTTPException(40x, detail=...)` |
| Документация | Никакой | Swagger UI на `/docs` |

## OpenAPI и Swagger UI

FastAPI **автоматически** строит OpenAPI-спецификацию (JSON-схему API) из:

- Сигнатур функций-роутов (типы аргументов, возвращаемое значение).
- Pydantic-схем.
- Декораторов (`@router.post("/", response_model=...)`).

Спецификация доступна на:

- **`/openapi.json`** — сырой JSON (например, для генерации клиентских SDK).
- **`/docs`** — интерактивный Swagger UI: можно прямо в браузере выполнять запросы.
- **`/redoc`** — альтернативный, более «бумажный» вид той же спецификации.

Это включается одной строкой в [app/main.py:18-19](../app/main.py#L18-L19):

```python
docs_url="/docs",
redoc_url="/redoc",
```

Если их выключить (`docs_url=None`), Swagger исчезнет — иногда нужно в проде, чтобы не показывать структуру API.

## Стиль HTTP-кодов

| Ситуация | Код | Где |
|---|---|---|
| OK + объект | 200 | по умолчанию |
| Создан ресурс | 201 | `status_code=201` (`POST /tasks`, `POST /auth/register`) |
| Не авторизован | 401 | `HTTPException(401, ...)` |
| Доступ запрещён | 403 | `has_permission(...) == False` → 403 |
| Не найдено | 404 | `crud.get_task_by_id(...) is None` → 404 |
| Конфликт | 409 | email уже занят при регистрации |
| Невалидный payload | 422 | автоматически из Pydantic |
| Ошибка сервера | 500 | необработанное исключение |

## Технологии под капотом

### REST
Архитектурный стиль API: ресурсы (URL'ы существительных), действия — HTTP-методами (`GET`, `POST`, `PUT`/`PATCH`, `DELETE`). Состояние клиента не хранится на сервере (хотя cookie — компромисс). Простой и универсальный, потому и стал стандартом.

### OpenAPI / Swagger
**OpenAPI** — формат описания HTTP-API в JSON или YAML. **Swagger UI** — браузерный клиент, который рисует интерактивную документацию из этого описания. FastAPI генерирует OpenAPI «из коробки» — это его самое мощное преимущество перед Flask/Django.

### Pydantic
Библиотека для описания структур данных через тип-аннотации Python. Под капотом — Rust-ускоренная валидация (с версии 2.0). FastAPI использует её и для входа, и для выхода.

### JWT bearer authentication
Схема: клиент шлёт JWT в заголовке `Authorization: Bearer <token>`. Сервер декодирует и проверяет подпись. Stateless — на сервере не нужно хранить сессии. Минус — невозможно «отозвать» токен (если только не вести список чёрных).

### OAuth2 password grant
Один из «потоков» в OAuth2. Клиент отправляет логин + пароль и получает access-token. Считается legacy (рекомендуют PKCE-flow), но прост в реализации, и FastAPI его поддерживает «из коробки» через `OAuth2PasswordBearer` + `OAuth2PasswordRequestForm`.

## Что почитать

- [FastAPI — Tutorial / First steps](https://fastapi.tiangolo.com/tutorial/first-steps/) — поэтапный туториал, лучшее введение в FastAPI.
- [FastAPI — Path / Query / Body parameters](https://fastapi.tiangolo.com/tutorial/path-params/) — как валидируются входные данные.
- [FastAPI — Response Model](https://fastapi.tiangolo.com/tutorial/response-model/) — как работает `response_model=...`.
- [FastAPI — OAuth2 with Password (and hashing), Bearer with JWT tokens](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/) — каноническая статья про нашу схему JWT.
- [Pydantic v2 documentation](https://docs.pydantic.dev/latest/) — особенно `Field`, `Model Config`, `EmailStr`, validators.
- [OpenAPI Specification](https://swagger.io/specification/) — формат, который FastAPI генерирует.
- [REST API Tutorial — REST Architectural Constraints](https://restfulapi.net/rest-architectural-constraints/) — про сами принципы REST.
- [Habr — Понимаем JWT за 10 минут](https://habr.com/ru/companies/maxilect/articles/672336/) — краткое введение на русском.
