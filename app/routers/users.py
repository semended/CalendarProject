import base64
import os
import re
from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import availability, crud
from app.config import ALLOWED_EXTENSIONS, UPLOAD_FOLDER
from app.database import get_db
from app.deps import get_current_user, get_current_user_optional
from app.models import User
from app.permissions import P_VIEW, has_permission
from app.services import user_service
from app.templating import templates

# Жёсткая валидация цвета перед подстановкой в style="" — Jinja autoescape
# защищает HTML-контекст, но не CSS-значения. Без regex кто-то может
# записать в Task.color что-то, что сломает разметку.
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def _safe_color(value: Optional[str], default: str = "#0ea5e9") -> str:
    return value if value and _HEX_COLOR_RE.match(value) else default

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
async def settings_get(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await crud.get_tasks_by_user_id(db, user.id, roots_only=True)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"user": user, "tasks": tasks},
    )


@router.post("/user/settings")
async def settings_post(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    user_id = user.id
    old_avatar_path = _avatar_path_for(user.avatar_url)

    # 1) remove_avatar
    if form.get("remove_avatar") == "true":
        _remove_if_exists(old_avatar_path)
        await crud.update_user_avatar(db, user_id, "")
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

    await user_service.update_profile(db, user_id, user_dict)
    return RedirectResponse(url="/user/settings", status_code=303)


@router.get("/user/{user_id}/gantt", name="user_gantt_page")
async def user_gantt_get(
    request: Request,
    user_id: int,
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Гант задач, где данный юзер — assignee_id.

    Плоский (без дерева подзадач): одна задача = одна полоска. Берём только
    непомеченные удалёнными и видимые viewer'у через P_VIEW (с наследованием
    по дереву задач). Без P_VIEW-фильтра был бы кросс-проектный лик: любой
    залогиненный юзер видел бы имена/дедлайны задач из проектов, куда его
    не приглашали.
    """
    target = await crud.get_user_by_id(db, user_id)
    if target is None:
        return templates.TemplateResponse(request, "not_found.html", status_code=404)

    assigned = await crud.get_tasks_by_assignee(db, target.id)
    visible: list = []
    for t in assigned:
        if await has_permission(db, viewer.id, t.id, P_VIEW):
            visible.append(t)
    tasks_sidebar = await crud.get_tasks_by_user_id(db, viewer.id, roots_only=True)

    now = datetime.now()
    starts = [t.created_at for t in visible if t.created_at]
    ends = [t.ended_at for t in visible if t.ended_at]
    start = min(starts) if starts else now
    end = max(ends) if ends else (start + timedelta(days=30))
    if end <= start:
        end = start + timedelta(days=30)
    total_seconds = max((end - start).total_seconds(), 1.0)

    def pct(dt: datetime) -> float:
        return max(0.0, min(100.0, (dt - start).total_seconds() / total_seconds * 100.0))

    # Сортируем по дедлайну: ближайшие сверху, без срока — в конец. Так юзер
    # сразу видит, что горит, а не получает рандомный порядок из БД.
    visible_sorted = sorted(
        visible,
        key=lambda t: (t.ended_at is None, t.ended_at or datetime.max),
    )

    rows = []
    for t in visible_sorted:
        t_start = t.created_at or start
        t_end = t.ended_at or end
        left = pct(t_start)
        width = max(1.5, pct(t_end) - left)
        if t.state == "done":
            cls = "done"
        elif t.ended_at and t.ended_at < now:
            cls = "overdue"
        else:
            cls = "open"
        rows.append({
            "task": t,
            "left": round(left, 2),
            "width": round(width, 2),
            "cls": cls,
            "color": _safe_color(t.color),
        })

    today_pct = round(pct(now), 2) if start <= now <= end else None
    axis_ticks = [
        (start + timedelta(seconds=total_seconds * i / 6)).strftime("%d.%m")
        for i in range(6)
    ]

    return templates.TemplateResponse(
        request,
        "user_gantt.html",
        {
            "active_page": "user_gantt",
            "user": viewer,
            "target": target,
            "is_self": viewer.id == target.id,
            "tasks": tasks_sidebar,
            "rows": rows,
            "axis_ticks": axis_ticks,
            "today_pct": today_pct,
            "range_label": f"{start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}",
        },
    )


@router.get("/user/{user_id}/schedule", name="user_schedule_page")
async def schedule_get(
    request: Request,
    user_id: int,
    week: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    target = await crud.get_user_by_id(db, user_id)
    viewer = await get_current_user_optional(request, db)
    if target is None:
        return templates.TemplateResponse(request, "not_found.html", status_code=404)
    if viewer is None:
        return RedirectResponse(url="/", status_code=303)

    if week:
        try:
            anchor = date.fromisoformat(week)
        except ValueError:
            anchor = date.today()
    else:
        anchor = date.today()

    is_self = viewer.id == target.id
    rendered = await availability.render_week(db, target.id, anchor, is_self)
    tasks = await crud.get_tasks_by_user_id(db, viewer.id, roots_only=True)
    prev_week = (availability.week_start(anchor) - timedelta(days=7)).isoformat()
    next_week = (availability.week_start(anchor) + timedelta(days=7)).isoformat()
    today_iso = date.today().isoformat()

    return templates.TemplateResponse(
        request,
        "schedule.html",
        {
            "user": viewer,
            "target": target,
            "tasks": tasks,
            "days": rendered["days"],
            "hours": rendered["hours"],
            "grid": rendered["grid"],
            "slots": rendered["slots"],
            "prev_week": prev_week,
            "next_week": next_week,
            "today_iso": today_iso,
            "is_self": is_self,
        },
    )


@router.post("/user/{user_id}/schedule")
async def schedule_post(
    user_id: int,
    action: str = Form(...),
    slot_id: Optional[int] = Form(None),
    slot_date: Optional[str] = Form(None),
    start_time: Optional[str] = Form(None),
    end_time: Optional[str] = Form(None),
    kind: Optional[str] = Form("busy"),
    note: Optional[str] = Form(None),
    viewer: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if viewer.id != user_id:
        raise HTTPException(status_code=403, detail="Редактировать можно только свой график")

    if action == "delete" and slot_id is not None:
        await availability.delete_slot(db, slot_id, viewer.id)
    elif action == "add" and slot_date and start_time and end_time:
        try:
            d = date.fromisoformat(slot_date)
            st = datetime.combine(d, time.fromisoformat(start_time))
            et = datetime.combine(d, time.fromisoformat(end_time))
            if et > st:
                await availability.add_slot(db, viewer.id, st, et, kind or "busy", note)
        except ValueError:
            pass

    return RedirectResponse(url=f"/user/{user_id}/schedule?week={slot_date or ''}", status_code=303)


@router.get("/user/{user_id}", name="user_page")
async def user_page(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    target = await crud.get_user_by_id(db, user_id)
    viewer = await get_current_user_optional(request, db)
    if target is None:
        return templates.TemplateResponse(
            request, "not_found.html", status_code=404
        )
    tasks = await crud.get_tasks_by_user_id(db, viewer.id, roots_only=True) if viewer else []
    from app.visibility import PRIVACY_FIELDS, is_visible
    visible = {f: is_visible(target, viewer, f) for f in PRIVACY_FIELDS}
    is_self = viewer is not None and viewer.id == target.id
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": target,
            "viewer": viewer,
            "tasks": tasks,
            "visible": visible,
            "is_self": is_self,
        },
    )
