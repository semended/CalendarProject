from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.deps import get_current_user_api
from app.models import User
from app.permissions import P_VIEW, has_permission
from app.schemas import TaskCreate, TaskResponse, TaskUpdate
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=List[TaskResponse])
async def api_list_my_tasks(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    return await crud.get_tasks_by_user_id(db, user.id, limit=limit, offset=offset)


@router.post("", response_model=TaskResponse, status_code=201)
async def api_create_task(
    payload: TaskCreate,
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await task_service.create_task(
            db,
            user,
            name=payload.name,
            description=payload.description,
            color=payload.color,
            deadline=payload.ended_at,
            parent_task_id=payload.parent_task_id,
            assignee_id=payload.assignee_id,
            strict_assignee=True,
        )
    except task_service.PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except task_service.InvalidAssignee as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/{task_id}", response_model=TaskResponse)
async def api_get_task(
    task_id: int,
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    task = await crud.get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if not await has_permission(db, user.id, task_id, P_VIEW):
        raise HTTPException(status_code=403, detail="Нет доступа к этой задаче")
    return task


@router.get("/{task_id}/subtasks", response_model=List[TaskResponse])
async def api_list_subtasks(
    task_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    if not await has_permission(db, user.id, task_id, P_VIEW):
        raise HTTPException(status_code=403, detail="Нет доступа к этой задаче")
    return await crud.get_subtasks(db, task_id, limit=limit, offset=offset)


@router.patch("/{task_id}", response_model=TaskResponse)
async def api_update_task(
    task_id: int,
    payload: TaskUpdate,
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    apply_assignee = "assignee_id" in payload.model_fields_set
    apply_deadline = "ended_at" in payload.model_fields_set
    try:
        return await task_service.update_task(
            db,
            user,
            task_id,
            name=payload.name,
            description=payload.description,
            color=payload.color,
            state=payload.state,
            assignee_id=payload.assignee_id,
            apply_assignee=apply_assignee,
            strict_assignee=True,
            deadline=payload.ended_at,
            apply_deadline=apply_deadline,
        )
    except task_service.TaskNotFound:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    except task_service.PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except task_service.InvalidAssignee as exc:
        raise HTTPException(status_code=422, detail=str(exc))
