from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_db
from app.deps import get_current_user_api
from app.models import User
from app.permissions import (
    P_CREATE_SUBTASK,
    P_EDIT_SETTINGS,
    P_VIEW,
    has_permission,
)
from app.schemas import TaskCreate, TaskResponse, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])

# DB stores DateTime без tzinfo; нормализуем tz-aware payload'ы в локальное naive
def _naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


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
    if payload.parent_task_id is not None:
        if not await has_permission(db, user.id, payload.parent_task_id, P_CREATE_SUBTASK):
            raise HTTPException(status_code=403, detail="Нет прав на создание подзадачи")

    ended_at = _naive(payload.ended_at) if payload.ended_at is not None else None
    if ended_at is not None:
        duration = int((ended_at - datetime.now()).total_seconds())
    else:
        duration = 2_147_000_000

    assignee_id = payload.assignee_id
    if assignee_id is not None:
        candidates = await crud.get_assignee_candidates(db, payload.parent_task_id, user.id)
        if not any(c.id == assignee_id for c in candidates):
            raise HTTPException(
                status_code=422,
                detail="Этот пользователь не может быть назначен на задачу",
            )

    return await crud.create_task_bundle(
        db,
        creator_id=user.id,
        name=payload.name.strip(),
        description=payload.description.strip(),
        color=payload.color,
        duration=duration,
        parent_task_id=payload.parent_task_id,
        ended_at=ended_at,
        assignee_id=assignee_id,
    )


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
    task = await crud.get_task_by_id(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if not await has_permission(db, user.id, task_id, P_EDIT_SETTINGS):
        raise HTTPException(status_code=403, detail="Нет прав на редактирование задачи")

    if payload.name is not None or payload.description is not None or payload.color is not None:
        await crud.update_task_info(db, task_id, payload.name, payload.description, payload.color)

    if payload.assignee_id is not None:
        candidates = await crud.get_assignee_candidates(db, task_id, user.id)
        if not any(c.id == payload.assignee_id for c in candidates):
            raise HTTPException(
                status_code=422,
                detail="Этот пользователь не может быть назначен на задачу",
            )
        await crud.update_task_assignee(db, task_id, payload.assignee_id)

    if payload.state is not None:
        await crud.update_task_state(db, task_id, payload.state)

    return await crud.get_task_by_id(db, task_id)
