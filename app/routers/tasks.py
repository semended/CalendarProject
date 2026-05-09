from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import availability, crud
from app.database import get_db
from app.deps import get_current_user
from app.models import Task, User
from app.permissions import (
    P_VIEW,
    has_permission,
    user_perms,
)
from app.permissions import ALL_PERMS
from app.services import roles_service, task_service
from app.templating import templates

router = APIRouter()

# UI-метки для кодов прав (источник кодов — app/permissions.py).
_PERM_LABELS = {
    "task.view": "Просмотр",
    "task.edit_settings": "Редактирование",
    "task.manage_members": "Управление участниками",
    "task.create_subtask": "Создание подзадач",
    "task.delete_subtask": "Удаление подзадач",
}


async def _decorate_tasks_with_counts(db: AsyncSession, tasks):
    for t in tasks:
        t.tasks = len(await crud.get_subtasks(db, t.id))
        t.members = len(await crud.get_users_in_task(db, t.id))
    return tasks


@router.get("/main", name="main_page")
async def main_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await crud.get_tasks_by_user_id(db, user.id, roots_only=True)
    await _decorate_tasks_with_counts(db, tasks)
    return templates.TemplateResponse(
        request,
        "main.html",
        {"active_page": "all_tasks", "user": user, "tasks": tasks},
    )


@router.get("/calendar", name="calendar_page")
async def calendar_page(
    request: Request,
    month: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    anchor = date.today()
    if month:
        try:
            anchor = date.fromisoformat(month + "-01")
        except ValueError:
            pass
    rendered = await availability.render_month(db, user.id, anchor)
    tasks = await crud.get_tasks_by_user_id(db, user.id, roots_only=True)

    first = rendered["month_first"]
    prev_first = (first - timedelta(days=1)).replace(day=1)
    if first.month == 12:
        next_first = first.replace(year=first.year + 1, month=1)
    else:
        next_first = first.replace(month=first.month + 1)

    month_names = [
        "январь", "февраль", "март", "апрель", "май", "июнь",
        "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
    ]

    return templates.TemplateResponse(
        request,
        "calendar.html",
        {
            "active_page": "calendar",
            "user": user,
            "tasks": tasks,
            "weeks": rendered["weeks"],
            "events_by_day": rendered["events_by_day"],
            "month_first": first,
            "month_label": f"{month_names[first.month - 1]} {first.year}",
            "prev_month": prev_first.strftime("%Y-%m"),
            "next_month": next_first.strftime("%Y-%m"),
            "this_month": date.today().strftime("%Y-%m"),
            "today": date.today(),
        },
    )


@router.get("/create_task", name="create_task_page")
@router.get("/create_task/{parent_task_id}", name="create_task_page")
async def create_task_get(
    request: Request,
    parent_task_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tasks = await crud.get_tasks_by_user_id(db, user.id, roots_only=True)
    candidates = await crud.get_assignee_candidates(db, parent_task_id, user.id)
    parent_task = await crud.get_task_by_id(db, parent_task_id) if parent_task_id else None
    return templates.TemplateResponse(
        request,
        "create_task.html",
        {
            "active_page": "create_task",
            "user": user,
            "tasks": tasks,
            "parent_task_id": parent_task_id,
            "parent_task": parent_task,
            "assignee_candidates": candidates,
        },
    )


@router.post("/create_task")
@router.post("/create_task/{parent_task_id}")
async def create_task_post(
    request: Request,
    parent_task_id: Optional[int] = None,
    parent_task_id_form: Optional[int] = Form(None, alias="parent_task_id"),
    taskName: str = Form(...),
    taskDescription: str = Form(""),
    taskColor: str = Form("#0ea5e9"),
    taskDeadline: Optional[str] = Form(None),
    assignee_id: Optional[int] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Поддерживаем оба способа передачи parent_task_id: через URL-path и через hidden-поле
    # формы (шаблон current_task.html шлёт POST на /create_task с hidden parent_task_id).
    effective_parent_id = parent_task_id if parent_task_id is not None else parent_task_id_form

    if not taskName or not taskName.strip():
        tasks = await crud.get_tasks_by_user_id(db, user.id, roots_only=True)
        candidates = await crud.get_assignee_candidates(db, effective_parent_id, user.id)
        return templates.TemplateResponse(
            request,
            "create_task.html",
            {
                "active_page": "create_task",
                "user": user,
                "tasks": tasks,
                "parent_task_id": effective_parent_id,
                "assignee_candidates": candidates,
                "error": "Название проекта обязательно для заполнения",
            },
        )

    deadline = datetime.fromisoformat(taskDeadline) if taskDeadline else None

    try:
        await task_service.create_task(
            db,
            user,
            name=taskName,
            description=taskDescription,
            color=taskColor,
            deadline=deadline,
            parent_task_id=effective_parent_id,
            assignee_id=assignee_id,
            strict_assignee=False,
        )
    except task_service.PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if effective_parent_id is not None:
        return RedirectResponse(url=f"/task/{effective_parent_id}", status_code=303)
    return RedirectResponse(url="/main", status_code=303)


@router.get("/task/{task_id}", name="task_page")
async def task_get(
    request: Request,
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    task = await crud.get_task_by_id(db, task_id)
    in_progress_tasks = await crud.get_subtasks(db, task_id)
    for t in in_progress_tasks:
        t.tasks = len(await crud.get_subtasks(db, t.id))
        t.members = len(await crud.get_users_in_task(db, t.id))
    tasks = await crud.get_tasks_by_user_id(db, user.id, roots_only=True)
    team = await crud.get_users_in_task(db, task_id)
    for member in team:
        member.role_name = await crud.get_user_role_in_task(db, member.id, task_id)

    return templates.TemplateResponse(
        request,
        "current_task.html",
        {
            "active_page": "current_task",
            "user": user,
            "task": task,
            "tasks": tasks,
            "in_progress_tasks": in_progress_tasks,
            "team": team,
            "perms": await user_perms(db, user.id, task_id),
        },
    )


@router.post("/task/{task_id}")
async def task_post(task_id: int, user: User = Depends(get_current_user)):
    # Original Flask behaviour: POST on /task/<id> redirects to create subtask.
    return RedirectResponse(url=f"/create_task/{task_id}", status_code=303)


@router.get("/task/{task_id}/overview", name="task_overview_page")
async def task_overview_get(
    request: Request,
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    root = await crud.get_task_by_id(db, task_id)
    tasks = await crud.get_tasks_by_user_id(db, user.id, roots_only=True)

    async def collect_descendants(node: Task):
        children = await crud.get_subtasks(db, node.id)
        out = []
        for c in children:
            out.append({"task": c, "children": await collect_descendants(c)})
        return out

    tree = await collect_descendants(root) if root else []

    # Палитра для треков первого уровня — используем, если у подзадачи
    # не задан явный color. В demo все подзадачи наследуют цвет корня,
    # поэтому без палитры все треки слились бы в один блоб.
    TRACK_PALETTE = [
        "#b84a28", "#5a7a4a", "#7c4a6b", "#a67f2a",
        "#2f6b89", "#9c4c2c", "#4f6d8c", "#7a5a2c",
    ]

    # Для каждого ряда: цвет цепочки (= track_id первого уровня),
    # чтобы зависимые таски красились одинаково, параллельные — по-разному.
    rows_raw = []  # (task, depth, track_id)

    def walk_tree(nodes, depth=0, track_id=None):
        for idx, n in enumerate(nodes):
            # track_id задаётся на первом уровне и наследуется вниз
            local_track = track_id if track_id is not None else idx
            rows_raw.append((n["task"], depth, local_track))
            walk_tree(n["children"], depth + 1, local_track)

    walk_tree(tree)

    now = datetime.now()
    starts = [root.created_at] if root and root.created_at else []
    ends = []
    for t, _, _ in rows_raw:
        if t.created_at:
            starts.append(t.created_at)
        if t.ended_at:
            ends.append(t.ended_at)

    start = min(starts) if starts else now
    fallback_end = start + timedelta(days=30)
    end = max(ends) if ends else fallback_end
    if end <= start:
        end = start + timedelta(days=30)
    total_seconds = max((end - start).total_seconds(), 1.0)

    def pct(dt: datetime) -> float:
        return max(0.0, min(100.0, (dt - start).total_seconds() / total_seconds * 100.0))

    # Цвет треков первого уровня: берём собственный color подзадачи,
    # только если он явно отличается от цвета корня (т.е. пользователь
    # его переопределил). Иначе — палитра по индексу трека.
    track_color_by_id: dict[int, str] = {}
    first_level = [n for n in tree]
    for i, n in enumerate(first_level):
        own = (n["task"].color or "").lower()
        root_color = (root.color or "").lower() if root else ""
        if own and own != root_color:
            track_color_by_id[i] = n["task"].color
        else:
            track_color_by_id[i] = TRACK_PALETTE[i % len(TRACK_PALETTE)]

    rows = []
    current_track = None
    for t, depth, track_id in rows_raw:
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
            "depth": depth,
            "left": round(left, 2),
            "width": round(width, 2),
            "cls": cls,
            "color": track_color_by_id.get(track_id, "#b84a28"),
            "track_start": track_id != current_track,
            "track_id": track_id,
        })
        current_track = track_id

    today_pct = round(pct(now), 2) if start <= now <= end else None

    axis_ticks = []
    for i in range(6):
        tick_dt = start + timedelta(seconds=total_seconds * i / 6)
        axis_ticks.append(tick_dt.strftime("%d.%m"))

    # Сводка треков для легенды
    track_legend = []
    for i, n in enumerate(first_level):
        track_legend.append({
            "name": n["task"].name,
            "color": track_color_by_id[i],
            "count": 1 + _count_descendants(n["children"]),
        })

    return templates.TemplateResponse(
        request,
        "task_overview.html",
        {
            "active_page": "current_task",
            "user": user,
            "task": root,
            "tasks": tasks,
            "tree": tree,
            "rows": rows,
            "axis_ticks": axis_ticks,
            "today_pct": today_pct,
            "range_label": f"{start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}",
            "track_legend": track_legend,
        },
    )


def _count_descendants(nodes) -> int:
    total = 0
    for n in nodes:
        total += 1 + _count_descendants(n["children"])
    return total


@router.get("/task_management/{task_id}", name="task_management_page")
async def task_management_get(
    request: Request,
    task_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await has_permission(db, user.id, task_id, P_VIEW):
        raise HTTPException(status_code=403, detail="Нет доступа к этой задаче")

    task = await crud.get_task_by_id(db, task_id)
    team = await crud.get_users_in_task(db, task_id)
    tasks = await crud.get_tasks_by_user_id(db, user.id, roots_only=True)
    for member in team:
        member.role_name = await crud.get_user_role_in_task(db, member.id, task_id)
    candidates = await crud.get_assignee_candidates(db, task_id, user.id)
    roles = await roles_service.list_roles(db, task_id)
    # Подготовим plain-структуру для шаблона: имя/перечень кодов прав/системность.
    roles_view = [
        {
            "id": r.id,
            "name": r.name,
            "is_system": r.is_system,
            "permissions": [p.permission for p in r.permissions],
        }
        for r in roles
    ]

    return templates.TemplateResponse(
        request,
        "task_management.html",
        {
            "active_page": "current_task",
            "user": user,
            "tasks": tasks,
            "task": task,
            "team": team,
            "assignee_candidates": candidates,
            "roles": roles_view,
            "all_permissions": list(ALL_PERMS),
            "perm_labels": _PERM_LABELS,
            "perms": await user_perms(db, user.id, task_id),
        },
    )


@router.post("/task_management/{task_id}")
async def task_management_post(
    request: Request,
    task_id: int,
    email: Optional[str] = Form(None),
    role_id: Optional[int] = Form(None),
    task_name: Optional[str] = Form(None),
    task_description: Optional[str] = Form(None),
    task_color: Optional[str] = Form(None),
    assignee_id: Optional[str] = Form(None),
    task_state: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if email is not None:
        try:
            await task_service.add_member(
                db, user, task_id, email=email, role_id=int(role_id) if role_id else 0
            )
        except task_service.PermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        return RedirectResponse(url=f"/task_management/{task_id}", status_code=303)

    new_assignee: Optional[int] = None
    apply_assignee = assignee_id is not None
    if apply_assignee and assignee_id and assignee_id.strip():
        new_assignee = int(assignee_id)

    state_to_set = task_state if (
        task_state and task_state in ("todo", "in_progress", "review", "done", "paused")
    ) else None

    try:
        await task_service.update_task(
            db,
            user,
            task_id,
            name=task_name,
            description=task_description,
            color=task_color,
            state=state_to_set,
            assignee_id=new_assignee,
            apply_assignee=apply_assignee,
            strict_assignee=False,
        )
    except task_service.TaskNotFound:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    except task_service.PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    return RedirectResponse(url=f"/task_management/{task_id}", status_code=303)


# ----- управление ролями проекта (Jinja-формы) -----

@router.post("/task_management/{task_id}/roles", name="role_create")
async def role_create_post(
    task_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    name = (form.get("role_name") or "").strip()
    perms = form.getlist("permissions") if hasattr(form, "getlist") else []
    try:
        await roles_service.create_custom_role(
            db, user, task_id, name=name, permissions=perms
        )
    except roles_service.PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except roles_service.InvalidRoleName:
        # просто редиректим назад — UX чистый, валидация на стороне формы
        pass
    return RedirectResponse(url=f"/task_management/{task_id}", status_code=303)


@router.post("/task_management/{task_id}/roles/{role_id}", name="role_update")
async def role_update_post(
    task_id: int,
    role_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    action = form.get("action") or "update"
    if action == "delete":
        try:
            await roles_service.delete_role(db, user, role_id)
        except roles_service.PermissionDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except roles_service.SystemRoleProtected as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except roles_service.RoleNotFound:
            raise HTTPException(status_code=404, detail="Роль не найдена")
        return RedirectResponse(url=f"/task_management/{task_id}", status_code=303)

    new_name = form.get("role_name")
    perms = form.getlist("permissions") if hasattr(form, "getlist") else []
    try:
        await roles_service.update_role(
            db, user, role_id,
            name=new_name if new_name is not None else None,
            permissions=perms,  # пустой список = снять все права
        )
    except roles_service.PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except roles_service.SystemRoleProtected as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except roles_service.RoleNotFound:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    except roles_service.InvalidRoleName:
        pass
    return RedirectResponse(url=f"/task_management/{task_id}", status_code=303)
