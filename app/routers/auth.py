from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.deps import get_current_user_optional, login_session, logout_session
from app.security import hash_password, is_hashed, verify_password
from app.templating import templates

router = APIRouter()


@router.get("/", name="start_page")
def start_page_get(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db)
    if user is not None:
        return RedirectResponse(url="/main", status_code=303)
    return templates.TemplateResponse("start.html", {"request": request})


@router.post("/", name="start_page")
def start_page_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = crud.get_user_by_email(db, email)
    if user is None:
        return templates.TemplateResponse(
            "start.html", {"request": request, "error": "Неправильный логин"}
        )
    if not verify_password(password, user.password):
        return templates.TemplateResponse(
            "start.html", {"request": request, "error": "Неправильный пароль"}
        )

    # upgrade legacy plaintext record on successful login
    if not is_hashed(user.password):
        crud.update_user_password(db, user.id, hash_password(password))

    login_session(request, user)
    return RedirectResponse(url="/main", status_code=303)


@router.get("/registration", name="register_page")
def register_page_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/registration", name="register_page")
def register_page_post(
    request: Request,
    email: str = Form(...),
    name: str = Form(...),
    surname: str = Form(...),
    password: str = Form(...),
    patronymic: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if crud.get_user_by_email(db, email) is not None:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Пользователь с такой почтой уже существует!"},
        )

    user = crud.add_user(
        db,
        email=email,
        name=name,
        surname=surname,
        password=hash_password(password),
        patronymic=patronymic,
    )
    login_session(request, user)
    return RedirectResponse(url="/main", status_code=303)


@router.get("/logout", name="exit_page")
def logout(request: Request):
    logout_session(request)
    return RedirectResponse(url="/", status_code=303)
