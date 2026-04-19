from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.deps import get_current_user_api, get_current_user_optional
from app.models import User
from app.schemas import UserMe, UserPublic
from app.visibility import PRIVACY_FIELDS, is_visible

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMe)
def api_users_me(user: User = Depends(get_current_user_api)):
    return user


@router.get("/{user_id}", response_model=UserPublic)
def api_users_get(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    target = crud.get_user_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    viewer = get_current_user_optional(request, db)

    # Всегда-публичные поля (нет соответствующих privacy_* настроек в модели).
    # Если позже появятся privacy_patronymic / privacy_pronouns / privacy_url / privacy_avatar_url —
    # их нужно прогнать через is_visible() так же, как поля из PRIVACY_FIELDS ниже.
    data = {
        "id": target.id,
        "name": target.name,
        "surname": target.surname,
        "patronymic": target.patronymic,
        "avatar_url": target.avatar_url,
        "pronouns": target.pronouns,
        "url": target.url,
    }
    for field in PRIVACY_FIELDS:
        if is_visible(target, viewer, field):
            data[field] = getattr(target, field)
    return UserPublic(**data)
