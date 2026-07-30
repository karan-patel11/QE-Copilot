"""User and role management routes.

Guards name permissions rather than roles (ADR-0105). The services called below
re-assert the same permissions, so authorisation does not depend on the router
staying correct.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from qe_api.dependencies import PrincipalDep, SessionDep, require
from qe_api.schemas import (
    Page,
    RoleAssignment,
    RoleRead,
    UserCreate,
    UserRead,
    UserUpdate,
)
from qe_api.services import users as user_service
from qe_api.services.support import DEFAULT_LIMIT, MAX_LIMIT
from qe_auth import Permission, Principal

router = APIRouter(prefix="/users", tags=["users"])
roles_router = APIRouter(prefix="/roles", tags=["users"])

LimitDep = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
OffsetDep = Annotated[int, Query(ge=0)]


@router.get("", response_model=Page[UserRead], summary="List users in the organisation")
async def list_users(
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.USER_READ))],
    limit: LimitDep = DEFAULT_LIMIT,
    offset: OffsetDep = 0,
) -> Page[UserRead]:
    users, total = await user_service.list_users(session, principal, limit=limit, offset=offset)
    return Page(
        items=[UserRead.from_user(user) for user in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user (administrators only)",
)
async def create_user(
    payload: UserCreate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.USER_WRITE))],
) -> UserRead:
    user = await user_service.create_user(
        session,
        principal,
        email=str(payload.email),
        full_name=payload.full_name,
        roles=payload.roles,
    )
    return UserRead.from_user(user)


@router.get("/{user_id}", response_model=UserRead, summary="Fetch a user")
async def get_user(
    user_id: uuid.UUID,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.USER_READ))],
) -> UserRead:
    return UserRead.from_user(await user_service.get_user(session, principal, user_id))


@router.patch("/{user_id}", response_model=UserRead, summary="Update a user")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.USER_WRITE))],
) -> UserRead:
    user = await user_service.update_user(
        session,
        principal,
        user_id,
        full_name=payload.full_name,
        is_active=payload.is_active,
    )
    return UserRead.from_user(user)


@router.put("/{user_id}/roles", response_model=UserRead, summary="Replace a user's roles")
async def set_user_roles(
    user_id: uuid.UUID,
    payload: RoleAssignment,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.ROLE_ASSIGN))],
) -> UserRead:
    user = await user_service.set_user_roles(session, principal, user_id, payload.roles)
    return UserRead.from_user(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a user")
async def delete_user(
    user_id: uuid.UUID,
    session: SessionDep,
    principal: Annotated[Principal, Depends(require(Permission.USER_WRITE))],
) -> Response:
    await user_service.delete_user(session, principal, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@roles_router.get("", response_model=list[RoleRead], summary="List assignable roles")
async def list_roles(session: SessionDep, principal: PrincipalDep) -> list[RoleRead]:
    rows = await user_service.list_roles(session, principal)
    return [RoleRead.model_validate(row) for row in rows]


__all__ = ["roles_router", "router"]
