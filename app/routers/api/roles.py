"""API под кастомные роли: список / создание / редактирование / удаление.

Чтение разрешено любому, кто имеет VIEW на проекте; изменения требуют
MANAGE_MEMBERS на корневом проекте (учитывая наследование).
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user_api
from app.models import User
from app.permissions import ALL_PERMS, P_VIEW, has_permission
from app.schemas import RoleCreate, RoleResponse, RoleUpdate
from app.services import roles_service

router = APIRouter(tags=["roles"])


def _to_response(role) -> RoleResponse:
    return RoleResponse(
        id=role.id,
        task_id=role.task_id,
        name=role.name,
        is_system=role.is_system,
        permissions=[p.permission for p in role.permissions],
    )


@router.get("/permissions", response_model=List[str])
async def api_list_known_permissions():
    """Список известных кодов прав — для UI с чекбоксами."""
    return list(ALL_PERMS)


@router.get("/tasks/{task_id}/roles", response_model=List[RoleResponse])
async def api_list_roles(
    task_id: int,
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    if not await has_permission(db, user.id, task_id, P_VIEW):
        raise HTTPException(status_code=403, detail="Нет доступа к этому проекту")
    roles = await roles_service.list_roles(db, task_id)
    return [_to_response(r) for r in roles]


@router.post("/tasks/{task_id}/roles", response_model=RoleResponse, status_code=201)
async def api_create_role(
    task_id: int,
    payload: RoleCreate,
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    try:
        role = await roles_service.create_custom_role(
            db, user, task_id, name=payload.name, permissions=payload.permissions
        )
    except roles_service.PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except roles_service.InvalidRoleName as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _to_response(role)


@router.patch("/roles/{role_id}", response_model=RoleResponse)
async def api_update_role(
    role_id: int,
    payload: RoleUpdate,
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    try:
        role = await roles_service.update_role(
            db, user, role_id, name=payload.name, permissions=payload.permissions
        )
    except roles_service.RoleNotFound:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    except roles_service.PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except roles_service.SystemRoleProtected as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except roles_service.InvalidRoleName as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _to_response(role)


@router.delete("/roles/{role_id}", status_code=204)
async def api_delete_role(
    role_id: int,
    user: User = Depends(get_current_user_api),
    db: AsyncSession = Depends(get_db),
):
    try:
        await roles_service.delete_role(db, user, role_id)
    except roles_service.RoleNotFound:
        raise HTTPException(status_code=404, detail="Роль не найдена")
    except roles_service.PermissionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except roles_service.SystemRoleProtected as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return None
