from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import APP_BASE_URL
from app.database import get_db
from app.deps import get_current_user, get_current_user_optional, login_session, logout_session
from app.email import send_email, send_verification_email
from app.models import User
from app.security import hash_password
from app.services import auth_service
from app.templating import templates
from app.tokens import (
    TokenError,
    make_reset_token,
    read_reset_token,
    read_verify_token,
)

router = APIRouter()


def _send_password_reset_email(user: User) -> None:
    token = make_reset_token(user.email)
    link = f"{APP_BASE_URL}/password-reset/{token}"
    send_email(
        to=user.email,
        subject="Восстановление пароля — CalendarProject",
        body=(
            f"Привет, {user.name}!\n\n"
            "Чтобы задать новый пароль, перейди по ссылке (действует 1 час):\n"
            f"{link}\n\n"
            "Если не просил восстановление — просто проигнорируй это письмо, "
            "твой пароль не изменится."
        ),
    )


# ---------- login / logout ----------

@router.get("/", name="start_page")
async def start_page_get(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_current_user_optional(request, db)
    if user is not None:
        return RedirectResponse(url="/main", status_code=303)
    return templates.TemplateResponse(request, "start.html")


@router.post("/", name="start_page")
async def start_page_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await auth_service.authenticate(db, email, password)
    except auth_service.InvalidCredentials:
        # Сохраняем прежнее UX-поведение: разное сообщение для "юзер не найден"
        # vs "пароль не подошёл" — для учебной демки это удобнее, чем
        # security-by-obscurity на странице логина.
        existing = await crud.get_user_by_email(db, email)
        message = "Неправильный логин" if existing is None else "Неправильный пароль"
        return templates.TemplateResponse(
            request, "start.html", {"error": message}
        )

    login_session(request, user)
    await auth_service.record_login(db, user)
    return RedirectResponse(url="/main", status_code=303)


@router.get("/logout", name="exit_page")
async def logout(request: Request):
    logout_session(request)
    return RedirectResponse(url="/", status_code=303)


# ---------- registration + email verification ----------

@router.get("/registration", name="register_page")
async def register_page_get(request: Request):
    return templates.TemplateResponse(request, "register.html")


@router.post("/registration", name="register_page")
async def register_page_post(
    request: Request,
    email: str = Form(...),
    name: str = Form(...),
    surname: str = Form(...),
    password: str = Form(...),
    patronymic: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await auth_service.register(
            db,
            email=email,
            name=name,
            surname=surname,
            password=password,
            patronymic=patronymic,
        )
    except auth_service.UserAlreadyExists:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"error": "Пользователь с такой почтой уже существует!"},
        )
    login_session(request, user)
    await auth_service.record_login(db, user)
    return RedirectResponse(url="/main", status_code=303)


@router.get("/verify-email/{token}", name="verify_email")
async def verify_email(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    try:
        email = read_verify_token(token)
    except TokenError:
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Ссылка невалидна",
                "message": "Ссылка для подтверждения почты устарела или повреждена. "
                           "Запроси новую из настроек.",
            },
            status_code=400,
        )

    user = await crud.get_user_by_email(db, email)
    if user is None:
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Пользователь не найден",
                "message": "Аккаунт, привязанный к этой ссылке, больше не существует.",
            },
            status_code=404,
        )

    if not user.confirmed:
        await crud.mark_user_confirmed(db, user.id)

    return templates.TemplateResponse(
        request,
        "auth_message.html",
        {
            "title": "Почта подтверждена",
            "message": "Готово. Можешь пользоваться аккаунтом.",
        },
    )


@router.post("/resend-verification", name="resend_verification")
async def resend_verification(user: User = Depends(get_current_user)):
    if not user.confirmed:
        send_verification_email(user.email, user.name)
    return RedirectResponse(url="/main", status_code=303)


# ---------- password reset ----------

@router.get("/password-reset", name="password_reset_request")
async def password_reset_request_get(request: Request):
    return templates.TemplateResponse(
        request, "password_reset_request.html"
    )


@router.post("/password-reset", name="password_reset_request")
async def password_reset_request_post(
    request: Request,
    email: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await crud.get_user_by_email(db, email)
    if user is not None:
        _send_password_reset_email(user)
    # intentionally no leak whether user exists
    return templates.TemplateResponse(
        request,
        "password_reset_request.html",
        {
            "sent": True,
            "email": email,
        },
    )


@router.get("/password-reset/{token}", name="password_reset_confirm")
async def password_reset_confirm_get(
    request: Request, token: str, db: AsyncSession = Depends(get_db)
):
    try:
        email = read_reset_token(token)
    except TokenError:
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Ссылка невалидна",
                "message": "Ссылка для сброса пароля устарела (живёт 1 час) или повреждена. "
                           "Запроси новую.",
            },
            status_code=400,
        )

    user = await crud.get_user_by_email(db, email)
    if user is None:
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Пользователь не найден",
                "message": "Аккаунт не найден.",
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        request,
        "password_reset_confirm.html",
        {"token": token},
    )


@router.post("/password-reset/{token}", name="password_reset_confirm")
async def password_reset_confirm_post(
    request: Request,
    token: str,
    password: str = Form(...),
    password2: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        email = read_reset_token(token)
    except TokenError:
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Ссылка невалидна",
                "message": "Ссылка устарела. Запроси сброс заново.",
            },
            status_code=400,
        )

    if password != password2:
        return templates.TemplateResponse(
            request,
            "password_reset_confirm.html",
            {"token": token, "error": "Пароли не совпадают"},
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            request,
            "password_reset_confirm.html",
            {"token": token, "error": "Пароль должен быть не короче 6 символов"},
        )

    user = await crud.get_user_by_email(db, email)
    if user is None:
        return templates.TemplateResponse(
            request,
            "auth_message.html",
            {
                "title": "Пользователь не найден",
                "message": "Аккаунт не найден.",
            },
            status_code=404,
        )

    await crud.update_user_password(db, user.id, hash_password(password))
    logout_session(request)
    return templates.TemplateResponse(
        request,
        "auth_message.html",
        {
            "title": "Пароль обновлён",
            "message": "Теперь залогинься с новым паролем.",
            "login_link": True,
        },
    )
