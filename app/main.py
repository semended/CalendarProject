from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
import os

from app.config import SECRET_KEY, UPLOAD_FOLDER
from app.deps import RedirectToLogin
from app.routers import auth, tasks, users
from app.routers.api import api_router
from app.templating import templates

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = FastAPI(
    title="CalendarProject",
    description="Web app for managing projects and tasks. HTML pages use Jinja; JSON API lives under /api/v1.",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=60 * 60 * 24 * 30)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(users.router)
app.include_router(api_router)


@app.exception_handler(RedirectToLogin)
async def redirect_to_login(request: Request, exc: RedirectToLogin):
    return RedirectResponse(url="/", status_code=303)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse(request, "not_found.html", status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8080, reload=True)
