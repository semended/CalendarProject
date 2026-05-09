"""CSRF-защита для cookie-сессий.

Двойная авторизация: cookie-сессии нуждаются в CSRF (браузер сам приложит
куку к любой форме на нашем домене), JWT — нет (Authorization-заголовок
браузер автоматически не добавляет).

Алгоритм:
1. На каждый GET-запрос в session кладётся свежий csrf_token, если его нет.
2. Любой mutating-запрос (POST/PUT/PATCH/DELETE) на не-/api/v1/* обязан
   прислать токен в form-поле `csrf_token` или заголовке X-CSRF-Token.
3. JWT-запросы (Authorization: Bearer ...) — пропускаем без проверки.
4. /api/v1/* пропускаем тоже: там либо JWT, либо cookie + JSON-вызов
   через fetch(), которому браузер в no-cors режиме не позволит делать
   состояние-меняющие запросы без CORS-разрешения.

Включается флагом config.CSRF_ENFORCE (по умолчанию выключено для
обратной совместимости; включать в проде).
"""
import secrets
from typing import Awaitable, Callable
from urllib.parse import parse_qs

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse, Response

from app.config import CSRF_ENFORCE

CSRF_FIELD = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
CSRF_SESSION_KEY = "_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_csrf_token(request: Request) -> str:
    """Вернуть текущий CSRF-токен сессии; сгенерировать, если ещё не было."""
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not CSRF_ENFORCE:
            return await call_next(request)

        # Проставляем токен на любом запросе, чтобы шаблон мог его отдать.
        get_csrf_token(request)

        if request.method in SAFE_METHODS:
            return await call_next(request)
        # API под /api/v1/* — другая модель авторизации (JWT/JSON), CSRF не нужен.
        if request.url.path.startswith("/api/v1/"):
            return await call_next(request)
        # Bearer-токен → авторизация без cookie, CSRF неактуален.
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return await call_next(request)

        expected = request.session.get(CSRF_SESSION_KEY)
        submitted = request.headers.get(CSRF_HEADER)

        if not submitted:
            # Читаем body вручную, парсим как application/x-www-form-urlencoded
            # или multipart, потом проигрываем body обратно через _receive,
            # чтобы downstream-роут увидел нетронутый запрос. Альтернатива
            # (request.form()) безвозвратно потребляет _receive у этой задачи.
            content_type = request.headers.get("content-type", "")
            body = await request.body()
            if content_type.startswith("application/x-www-form-urlencoded"):
                parsed = parse_qs(body.decode("utf-8", errors="ignore"))
                values = parsed.get(CSRF_FIELD)
                if values:
                    submitted = values[0]
            elif content_type.startswith("multipart/form-data"):
                # multipart парсить вручную тяжело — ищем токен по
                # сигнатуре name="csrf_token". Грубо, но работает для
                # form-submit браузера и тестов.
                marker = b'name="csrf_token"'
                idx = body.find(marker)
                if idx != -1:
                    after = body[idx + len(marker):]
                    # формат: \r\n\r\n<value>\r\n--boundary
                    sep = b"\r\n\r\n"
                    start = after.find(sep)
                    if start != -1:
                        end = after.find(b"\r\n", start + len(sep))
                        if end != -1:
                            submitted = after[start + len(sep):end].decode("utf-8", errors="ignore")
            # Restore body for downstream
            sent = False

            async def _receive():
                nonlocal sent
                if sent:
                    return {"type": "http.disconnect"}
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = _receive

        if not expected or not submitted or expected != submitted:
            return PlainTextResponse(
                "CSRF-токен отсутствует или неверен", status_code=403
            )

        return await call_next(request)
