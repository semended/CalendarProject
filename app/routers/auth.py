from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import APP_BASE_URL
from app.database import get_db
from app.deps import get_current_user, get_current_user_optional, login_session, logout_session
from app.email import send_email
from app.models import User
from app.security import hash_password, is_hashed, verify_password
from app.templating import templates
from app.tokens import (
    TokenError,
    make_reset_token,
    make_verify_token,
    read_reset_token,
    read_verify_token,
)

router = APIRouter()


# ---------- helpers ----------

def _send_verification_email(user: User) -> None:
    token = make_verify_token(user.email)
    link = f"{APP_BASE_URL}/verify-email/{token}"
    send_email(
        to=user.email,
        subject="Подтверждение почты — CalendarProject",
        body=(
            f"Привет, {user.name}!\n\n"
            "Чтобы подтвердить почту, перейди по ссылке ниже (действует 3 дня):\n"
            f"{link}\n\n"
            "Если ты не регистрировался на CalendarProject — просто проигнорируй это письмо."
        ),
    )


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
    return templates.TemplateResponse("start.html", {"request": request})


@router.post("/", name="start_page")
async def start_page_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await crud.get_user_by_email(db, email)
    if user is None:
        return templates.TemplateResponse(
            "start.html", {"request": request, "error": "Неправильный логин"}
        )
    if not verify_password(password, user.password):
        return templates.TemplateResponse(
            "start.html", {"request": request, "error": "Неправильный пароль"}
        )

    if not is_hashed(user.password):
        await crud.update_user_password(db, user.id, hash_password(password))

    login_session(request, user)
    return RedirectResponse(url="/main", status_code=303)


@router.get("/logout", name="exit_page")
async def logout(request: Request):
    logout_session(request)
    return RedirectResponse(url="/", status_code=303)


# ---------- registration + email verification ----------

@router.get("/registration", name="register_page")
async def register_page_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


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
    if await crud.get_user_by_email(db, email) is not None:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Пользователь с такой почтой уже существует!"},
        )

    user = await crud.add_user(
        db,
        email=email,
        name=name,
        surname=surname,
        password=hash_password(password),
        patronymic=patronymic,
    )
    _send_verification_email(user)
    login_session(request, user)
    return RedirectResponse(url="/main", status_code=303)


@router.get("/verify-email/{token}", name="verify_email")
async def verify_email(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    try:
        email = read_verify_token(token)
    except TokenError:
        return templates.TemplateResponse(
            "auth_message.html",
            {
                "request": request,
                "title": "Ссылка невалидна",
                "message": "Ссылка для подтверждения почты устарела или повреждена. "
                           "Запроси новую из настроек.",
            },
            status_code=400,
        )

    user = await crud.get_user_by_email(db, email)
    if user is None:
        return templates.TemplateResponse(
            "auth_message.html",
            {
                "request": request,
                "title": "Пользователь не найден",
                "message": "Аккаунт, привязанный к этой ссылке, больше не существует.",
            },
            status_code=404,
        )

    if not user.confirmed:
        await crud.mark_user_confirmed(db, user.id)

    return templates.TemplateResponse(
        "auth_message.html",
        {
            "request": request,
            "title": "Почта подтверждена",
            "message": "Готово. Можешь пользоваться аккаунтом.",
        },
    )


@router.post("/resend-verification", name="resend_verification")
async def resend_verification(user: User = Depends(get_current_user)):
    if not user.confirmed:
        _send_verification_email(user)
    return RedirectResponse(url="/main", status_code=303)


# ---------- password reset ----------

@router.get("/password-reset", name="password_reset_request")
async def password_reset_request_get(request: Request):
    return templates.TemplateResponse(
        "password_reset_request.html", {"request": request}
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
        "password_reset_request.html",
        {
            "request": request,
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
            "auth_message.html",
            {
                "request": request,
                "title": "Ссылка невалидна",
                "message": "Ссылка для сброса пароля устарела (живёт 1 час) или повреждена. "
                           "Запроси новую.",
            },
            status_code=400,
        )

    user = await crud.get_user_by_email(db, email)
    if user is None:
        return templates.TemplateResponse(
            "auth_message.html",
            {
                "request": request,
                "title": "Пользователь не найден",
                "message": "Аккаунт не найден.",
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        "password_reset_confirm.html",
        {"request": request, "token": token},
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
            "auth_message.html",
            {
                "request": request,
                "title": "Ссылка невалидна",
                "message": "Ссылка устарела. Запроси сброс заново.",
            },
            status_code=400,
        )

    if password != password2:
        return templates.TemplateResponse(
            "password_reset_confirm.html",
            {"request": request, "token": token, "error": "Пароли не совпадают"},
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            "password_reset_confirm.html",
            {"request": request, "token": token, "error": "Пароль должен быть не короче 6 символов"},
        )

    user = await crud.get_user_by_email(db, email)
    if user is None:
        return templates.TemplateResponse(
            "auth_message.html",
            {
                "request": request,
                "title": "Пользователь не найден",
                "message": "Аккаунт не найден.",
            },
            status_code=404,
        )

    await crud.update_user_password(db, user.id, hash_password(password))
    logout_session(request)
    return templates.TemplateResponse(
        "auth_message.html",
        {
            "request": request,
            "title": "Пароль обновлён",
            "message": "Теперь залогинься с новым паролем.",
            "login_link": True,
        },
    )
