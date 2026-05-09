import os
from pathlib import Path

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

_STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"


def _static_mtime(rel_path: str) -> str:
    try:
        return str(int((_STATIC_ROOT / rel_path).stat().st_mtime))
    except (OSError, ValueError):
        return "0"


def _url_for_ctx(request: Request):
    def _url_for(name: str, **kwargs):
        # Flask templates call url_for('static', filename=...); Starlette uses path=
        if name == "static" and "filename" in kwargs:
            filename = kwargs.pop("filename")
            url = request.url_for(name, path=filename)
            # cache-bust: ?v={mtime} — чтобы браузер не держал старую статику,
            # когда мы правим CSS/JS
            return f"{url}?v={_static_mtime(filename)}"
        return request.url_for(name, **kwargs)

    return {"url_for": _url_for}


def _csrf_ctx(request: Request):
    """Прокидываем csrf_token() как функцию (а не значение) — чтобы шаблон
    мог дёргать только там, где реально нужна форма (а не на каждой странице)."""
    from app.csrf import get_csrf_token

    def csrf_token() -> str:
        return get_csrf_token(request)

    return {"csrf_token": csrf_token}


templates = Jinja2Templates(
    directory="templates",
    context_processors=[_url_for_ctx, _csrf_ctx],
)
