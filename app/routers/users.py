import base64
import os
from typing import Optional

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import crud
from app.config import ALLOWED_EXTENSIONS, UPLOAD_FOLDER
from app.database import get_db
from app.deps import get_current_user, get_current_user_optional
from app.models import User
from app.templating import templates

router = APIRouter()


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _avatar_path_for(avatar_url: Optional[str]) -> Optional[str]:
    if not avatar_url:
        return None
    return os.path.join(UPLOAD_FOLDER, avatar_url + ".jpg")


def _remove_if_exists(path: Optional[str]) -> None:
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            print(f"Не удалось удалить {path}: {e}")


# NOTE: /user/settings must be registered before /user/{user_id:int}
# so the string "settings" doesn't get interpreted as a user id.

@router.get("/user/settings", name="settings_page")
def settings_get(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tasks = crud.get_tasks_by_user_id(db, user.id)
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "user": user, "tasks": tasks},
    )


@router.post("/user/settings")
async def settings_post(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    form = await request.form()
    user_id = user.id
    old_avatar_path = _avatar_path_for(user.avatar_url)

    # 1) remove_avatar
    if form.get("remove_avatar") == "true":
        _remove_if_exists(old_avatar_path)
        crud.update_user_avatar(db, user_id, "")
        return RedirectResponse(url="/user/settings", status_code=303)

    user_dict: dict = {}

    # 2) cropped base64
    cropped_image = form.get("cropped_image")
    if isinstance(cropped_image, str) and cropped_image.startswith("data:image"):
        try:
            _, encoded = cropped_image.split(",", 1)
            image_data = base64.b64decode(encoded)
            filename = f"user_{user_id}_avatar.jpg"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            with open(filepath, "wb") as f:
                f.write(image_data)
            if old_avatar_path and old_avatar_path != filepath:
                _remove_if_exists(old_avatar_path)
            user_dict["avatar_url"] = f"user_{user_id}_avatar"
        except Exception as e:
            print(f"Ошибка сохранения cropped аватара: {e}")

    # 3) file upload via input[type=file]
    else:
        upload = form.get("avatar")
        if isinstance(upload, UploadFile) and upload.filename and _allowed_file(upload.filename):
            try:
                filename = f"user_{user_id}_avatar.jpg"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                with open(filepath, "wb") as f:
                    f.write(await upload.read())
                if old_avatar_path and old_avatar_path != filepath:
                    _remove_if_exists(old_avatar_path)
                user_dict["avatar_url"] = f"user_{user_id}_avatar"
            except Exception as e:
                print(f"Ошибка сохранения файла аватара: {e}")

    # merge the rest of plain text fields
    for key, value in form.items():
        if isinstance(value, UploadFile):
            continue
        if key in ("cropped_image", "remove_avatar", "avatar"):
            continue
        user_dict[key] = value

    crud.update_user(db, user_id, user_dict)
    return RedirectResponse(url="/user/settings", status_code=303)


@router.get("/user/{user_id}", name="user_page")
def user_page(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
):
    target = crud.get_user_by_id(db, user_id)
    viewer = get_current_user_optional(request, db)
    if target is None:
        return templates.TemplateResponse(
            "not_found.html", {"request": request}, status_code=404
        )
    tasks = crud.get_tasks_by_user_id(db, viewer.id) if viewer else []
    return templates.TemplateResponse(
        "profile.html",
        {"request": request, "user": target, "tasks": tasks},
    )
