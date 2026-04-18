from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.templating import templates

router = APIRouter()


def _decorate_tasks_with_counts(db: Session, tasks):
    for t in tasks:
        t.tasks = len(crud.get_subtasks(db, t.id))
        t.members = len(crud.get_users_in_task(db, t.id))
    return tasks


@router.get("/main", name="main_page")
def main_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tasks = crud.get_tasks_by_user_id(db, user.id)
    _decorate_tasks_with_counts(db, tasks)
    return templates.TemplateResponse(
        "main.html",
        {"request": request, "active_page": "all_tasks", "user": user, "tasks": tasks},
    )


@router.get("/create_task", name="create_task_page")
@router.get("/create_task/{parent_task_id}", name="create_task_page")
def create_task_get(
    request: Request,
    parent_task_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tasks = crud.get_tasks_by_user_id(db, user.id)
    return templates.TemplateResponse(
        "create_task.html",
        {
            "request": request,
            "active_page": "create_task",
            "user": user,
            "tasks": tasks,
            "parent_task_id": parent_task_id,
        },
    )


@router.post("/create_task")
@router.post("/create_task/{parent_task_id}")
def create_task_post(
    request: Request,
    parent_task_id: Optional[int] = None,
    taskName: str = Form(...),
    taskDescription: str = Form(""),
    taskColor: str = Form("#0ea5e9"),
    taskDeadline: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not taskName or not taskName.strip():
        tasks = crud.get_tasks_by_user_id(db, user.id)
        return templates.TemplateResponse(
            "create_task.html",
            {
                "request": request,
                "active_page": "create_task",
                "user": user,
                "tasks": tasks,
                "error": "Название проекта обязательно для заполнения",
            },
        )

    if taskDeadline:
        ended_at = datetime.fromisoformat(taskDeadline)
        duration = int((ended_at - datetime.now()).total_seconds())
    else:
        ended_at = None
        duration = 2_147_000_000

    crud.create_task_bundle(
        db,
        creator_id=user.id,
        name=taskName.strip(),
        description=taskDescription.strip(),
        color=taskColor,
        duration=duration,
        parent_task_id=parent_task_id,
        ended_at=ended_at,
    )
    return RedirectResponse(url="/main", status_code=303)


@router.get("/task/{task_id}", name="task_page")
def task_get(
    request: Request,
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = crud.get_task_by_id(db, task_id)
    in_progress_tasks = crud.get_subtasks(db, task_id)
    for t in in_progress_tasks:
        t.tasks = len(crud.get_subtasks(db, t.id))
        t.members = len(crud.get_users_in_task(db, t.id))
    tasks = crud.get_tasks_by_user_id(db, user.id)
    team = crud.get_users_in_task(db, task_id)
    for member in team:
        member.role_name = crud.get_user_role_in_task(db, member.id, task_id)

    return templates.TemplateResponse(
        "current_task.html",
        {
            "request": request,
            "active_page": "current_task",
            "user": user,
            "task": task,
            "tasks": tasks,
            "in_progress_tasks": in_progress_tasks,
            "team": team,
        },
    )


@router.post("/task/{task_id}")
def task_post(task_id: int, user: User = Depends(get_current_user)):
    # Original Flask behaviour: POST on /task/<id> redirects to create subtask.
    return RedirectResponse(url=f"/create_task/{task_id}", status_code=303)


@router.get("/task_management/{task_id}", name="task_management_page")
def task_management_get(
    request: Request,
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = crud.get_task_by_id(db, task_id)
    team = crud.get_users_in_task(db, task_id)
    tasks = crud.get_tasks_by_user_id(db, user.id)
    for member in team:
        member.role_name = crud.get_user_role_in_task(db, member.id, task_id)

    return templates.TemplateResponse(
        "task_management.html",
        {
            "request": request,
            "active_page": "current_task",
            "user": user,
            "tasks": tasks,
            "task": task,
            "team": team,
        },
    )


@router.post("/task_management/{task_id}")
def task_management_post(
    request: Request,
    task_id: int,
    email: Optional[str] = Form(None),
    role_id: Optional[int] = Form(None),
    task_name: Optional[str] = Form(None),
    task_description: Optional[str] = Form(None),
    task_color: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if email is not None:
        target = crud.get_user_by_email(db, email)
        if target is None:
            return RedirectResponse(url=f"/task_management/{task_id}", status_code=303)
        # TODO: валидация что role_id принадлежит этой таске
        crud.assign_user_to_task_role(db, target.id, task_id, int(role_id))
        return RedirectResponse(url=f"/task_management/{task_id}", status_code=303)

    crud.update_task_info(db, task_id, task_name, task_description, task_color)
    return RedirectResponse(url=f"/task_management/{task_id}", status_code=303)
