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
    P_CREATE_SUBTASK,
    P_EDIT_SETTINGS,
    P_MANAGE_MEMBERS,
    P_VIEW,
    has_permission,
    user_perms,
)
from app.templating import templates

router = APIRouter()


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
    tasks = await crud.get_tasks_by_user_id(db, user.id)
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
    tasks = await crud.get_tasks_by_user_id(db, user.id)

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
    tasks = await crud.get_tasks_by_user_id(db, user.id)
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
    taskName: str = Form(...),
    taskDescription: str = Form(""),
    taskColor: str = Form("#0ea5e9"),
    taskDeadline: Optional[str] = Form(None),
    assignee_id: Optional[int] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if parent_task_id is not None:
        if not await has_permission(db, user.id, parent_task_id, P_CREATE_SUBTASK):
            raise HTTPException(status_code=403, detail="Нет прав на создание подзадачи")

    if not taskName or not taskName.strip():
        tasks = await crud.get_tasks_by_user_id(db, user.id)
        candidates = await crud.get_assignee_candidates(db, parent_task_id, user.id)
        return templates.TemplateResponse(
            request,
            "create_task.html",
            {
                "active_page": "create_task",
                "user": user,
                "tasks": tasks,
                "parent_task_id": parent_task_id,
                "assignee_candidates": candidates,
                "error": "Название проекта обязательно для заполнения",
            },
        )

    if taskDeadline:
        ended_at = datetime.fromisoformat(taskDeadline)
        duration = int((ended_at - datetime.now()).total_seconds())
    else:
        ended_at = None
        duration = 2_147_000_000

    if assignee_id is not None:
        candidates = await crud.get_assignee_candidates(db, parent_task_id, user.id)
        if not any(c.id == assignee_id for c in candidates):
            assignee_id = None

    await crud.create_task_bundle(
        db,
        creator_id=user.id,
        name=taskName.strip(),
        description=taskDescription.strip(),
        color=taskColor,
        duration=duration,
        parent_task_id=parent_task_id,
        ended_at=ended_at,
        assignee_id=assignee_id,
    )
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
    tasks = await crud.get_tasks_by_user_id(db, user.id)
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
    tasks = await crud.get_tasks_by_user_id(db, user.id)

    async def collect_descendants(node: Task):
        children = await crud.get_subtasks(db, node.id)
        out = []
        for c in children:
            out.append({"task": c, "children": await collect_descendants(c)})
        return out

    tree = await collect_descendants(root) if root else []

    flat = []

    def flatten(nodes, depth=0):
        for n in nodes:
            flat.append((n["task"], depth))
            flatten(n["children"], depth + 1)

    flatten(tree)

    now = datetime.now()
    starts = [root.created_at] if root and root.created_at else []
    ends = []
    for t, _ in flat:
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

    rows = []
    for t, depth in flat:
        t_start = t.created_at or start
        t_end = t.ended_at or end
        left = pct(t_start)
        width = max(1.5, pct(t_end) - left)
        if t.ended_at and t.ended_at < now:
            cls = "done"
        elif t.ended_at and t.ended_at < now + timedelta(days=1):
            cls = "overdue"
        else:
            cls = "open"
        rows.append({
            "task": t,
            "depth": depth,
            "left": round(left, 2),
            "width": round(width, 2),
            "cls": cls,
        })

    today_pct = round(pct(now), 2) if start <= now <= end else None

    axis_ticks = []
    for i in range(6):
        tick_dt = start + timedelta(seconds=total_seconds * i / 6)
        axis_ticks.append(tick_dt.strftime("%d.%m"))

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
        },
    )


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
    tasks = await crud.get_tasks_by_user_id(db, user.id)
    for member in team:
        member.role_name = await crud.get_user_role_in_task(db, member.id, task_id)
    candidates = await crud.get_assignee_candidates(db, task_id, user.id)

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
        if not await has_permission(db, user.id, task_id, P_MANAGE_MEMBERS):
            raise HTTPException(status_code=403, detail="Нет прав на управление участниками")
        target = await crud.get_user_by_email(db, email)
        if target is None:
            return RedirectResponse(url=f"/task_management/{task_id}", status_code=303)
        # TODO: валидация что role_id принадлежит этой таске
        await crud.assign_user_to_task_role(db, target.id, task_id, int(role_id))
        return RedirectResponse(url=f"/task_management/{task_id}", status_code=303)

    if not await has_permission(db, user.id, task_id, P_EDIT_SETTINGS):
        raise HTTPException(status_code=403, detail="Нет прав на редактирование задачи")

    await crud.update_task_info(db, task_id, task_name, task_description, task_color)

    if assignee_id is not None:
        new_assignee = int(assignee_id) if assignee_id.strip() else None
        if new_assignee is not None:
            candidates = await crud.get_assignee_candidates(db, task_id, user.id)
            if not any(c.id == new_assignee for c in candidates):
                new_assignee = None
        await crud.update_task_assignee(db, task_id, new_assignee)

    if task_state and task_state in ("todo", "in_progress", "review", "done", "paused"):
        await crud.update_task_state(db, task_id, task_state)

    return RedirectResponse(url=f"/task_management/{task_id}", status_code=303)
