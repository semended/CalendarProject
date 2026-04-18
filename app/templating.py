from fastapi.templating import Jinja2Templates
from starlette.requests import Request


def _url_for_ctx(request: Request):
    def _url_for(name: str, **kwargs):
        # Flask templates call url_for('static', filename=...); Starlette uses path=
        if name == "static" and "filename" in kwargs:
            kwargs = {"path": kwargs.pop("filename")}
        return request.url_for(name, **kwargs)

    return {"url_for": _url_for}


templates = Jinja2Templates(directory="templates", context_processors=[_url_for_ctx])
