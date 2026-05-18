from pathlib import Path

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.config import EMAIL_SMTP_HOST
from app.tokens import make_verify_token

_STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"


def _static_mtime(rel_path: str) -> str:
    try:
        return str(int((_STATIC_ROOT / rel_path).stat().st_mtime))
    except (OSError, ValueError):
        return "0"


def _relative(url) -> str:
    """Starlette `request.url_for` отдаёт абсолютный URL (scheme+host), а Flask —
    root-relative путь. Шаблоны и тесты писались под Flask-семантику
    (`href="/task/2"`, а не `http://host/task/2`), поэтому срезаем до path+query."""
    rel = url.path
    if url.query:
        rel = f"{rel}?{url.query}"
    return rel


def _url_for_ctx(request: Request):
    def _url_for(name: str, **kwargs):
        # Flask templates call url_for('static', filename=...); Starlette uses path=
        if name == "static" and "filename" in kwargs:
            filename = kwargs.pop("filename")
            url = request.url_for(name, path=filename)
            # cache-bust: ?v={mtime} — чтобы браузер не держал старую статику,
            # когда мы правим CSS/JS
            return f"{_relative(url)}?v={_static_mtime(filename)}"
        return _relative(request.url_for(name, **kwargs))

    return {"url_for": _url_for}


def _csrf_ctx(request: Request):
    """Прокидываем csrf_token() как функцию (а не значение) — чтобы шаблон
    мог дёргать только там, где реально нужна форма (а не на каждой странице)."""
    from app.csrf import get_csrf_token

    def csrf_token() -> str:
        return get_csrf_token(request)

    return {"csrf_token": csrf_token}


def _email_dev_ctx(request: Request):
    """Dev-fallback для подтверждения почты: если SMTP не настроен, шаблон
    рисует прямую verify-ссылку прямо в баннере «почта не подтверждена», чтобы
    юзер мог пройти подтверждение без реального почтового ящика.

    Возвращаем относительный путь — не зависит от APP_BASE_URL и работает на
    любом хосте/порте дев-сервера.
    """
    dev_mode = not EMAIL_SMTP_HOST

    def make_verify_link(email: str) -> str:
        return f"/verify-email/{make_verify_token(email)}"

    return {"email_dev_mode": dev_mode, "make_verify_link": make_verify_link}


templates = Jinja2Templates(
    directory="templates",
    context_processors=[_url_for_ctx, _csrf_ctx, _email_dev_ctx],
)
