"""User and role-assignment services.

Every query is filtered by ``principal.organisation_id`` (ADR-0106): a user in
another tenant is reported as *not found*, never as *forbidden*.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from qe_api.services.audit import record_audit
from qe_api.services.support import commit_or_conflict, flush_or_conflict
from qe_auth import Permission, Principal, Role
from qe_common.audit import AuditAction, AuditEntity
from qe_common.errors import ConflictError, NotFoundError, ValidationAppError
from qe_database.models import Role as RoleRow
from qe_database.models import User


async def _load_role_rows(session: AsyncSession, roles: Sequence[Role]) -> list[RoleRow]:
    if not roles:
        return []
    names = [role.value for role in roles]
    rows = list(
        (await session.execute(select(RoleRow).where(RoleRow.name.in_(names)))).scalars().all()
    )
    missing = sorted(set(names) - {row.name for row in rows})
    if missing:  # pragma: no cover - migration 0002 seeds every role
        raise ValidationAppError(f"Unknown role(s): {', '.join(missing)}")
    return rows


async def list_users(
    session: AsyncSession, principal: Principal, *, limit: int, offset: int
) -> tuple[list[User], int]:
    """Return one page of the caller's organisation's users, plus the total."""
    principal.require(Permission.USER_READ)
    scope = User.organisation_id == principal.organisation_id
    total = (
        await session.execute(select(func.count()).select_from(User).where(scope))
    ).scalar_one()
    stmt = (
        select(User)
        .where(scope)
        .options(selectinload(User.roles))
        .order_by(User.created_at, User.id)
        .limit(limit)
        .offset(offset)
    )
    return list((await session.execute(stmt)).scalars().all()), total


async def get_user(session: AsyncSession, principal: Principal, user_id: uuid.UUID) -> User:
    """Load one user from the caller's organisation."""
    principal.require(Permission.USER_READ)
    stmt = (
        select(User)
        .where(User.id == user_id, User.organisation_id == principal.organisation_id)
        .options(selectinload(User.roles))
    )
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found.")
    return user


async def create_user(
    session: AsyncSession,
    principal: Principal,
    *,
    email: str,
    full_name: str | None,
    roles: Sequence[Role],
) -> User:
    """Create a user inside the caller's organisation."""
    principal.require(Permission.USER_WRITE)
    if roles:
        principal.require(Permission.ROLE_ASSIGN)

    user = User(
        organisation_id=principal.organisation_id,
        email=email.strip().lower(),
        full_name=full_name,
        is_active=True,
    )
    user.roles.extend(await _load_role_rows(session, roles))
    session.add(user)
    await flush_or_conflict(session, "A user with that email already exists.")
    await record_audit(
        session,
        principal,
        action=AuditAction.CREATE,
        entity_type=AuditEntity.USER,
        entity_id=user.id,
        changes={"email": user.email, "roles": [role.value for role in roles]},
    )
    await commit_or_conflict(session, "A user with that email already exists.")
    return await get_user(session, principal, user.id)


async def update_user(
    session: AsyncSession,
    principal: Principal,
    user_id: uuid.UUID,
    *,
    full_name: str | None = None,
    is_active: bool | None = None,
) -> User:
    """Update mutable user attributes."""
    principal.require(Permission.USER_WRITE)
    user = await get_user(session, principal, user_id)
    changes: dict[str, object] = {}
    if full_name is not None:
        changes["full_name"] = {"from": user.full_name, "to": full_name}
        user.full_name = full_name
    if is_active is not None:
        if not is_active and user.id == principal.user_id:
            raise ConflictError("You cannot deactivate your own account.")
        changes["is_active"] = {"from": user.is_active, "to": is_active}
        user.is_active = is_active

    await flush_or_conflict(session, "User could not be updated.")
    await record_audit(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type=AuditEntity.USER,
        entity_id=user.id,
        changes=changes,
    )
    await commit_or_conflict(session, "User could not be updated.")
    return await get_user(session, principal, user_id)


async def set_user_roles(
    session: AsyncSession, principal: Principal, user_id: uuid.UUID, roles: Sequence[Role]
) -> User:
    """Replace a user's role set."""
    principal.require(Permission.ROLE_ASSIGN)
    user = await get_user(session, principal, user_id)
    if user.id == principal.user_id and Role.ADMINISTRATOR not in roles:
        # Guards against an administrator locking every admin out of the tenant.
        raise ConflictError("You cannot remove your own administrator role.")

    previous = sorted(row.name for row in user.roles)
    user.roles[:] = await _load_role_rows(session, roles)
    await flush_or_conflict(session, "Roles could not be assigned.")
    await record_audit(
        session,
        principal,
        action=AuditAction.UPDATE,
        entity_type=AuditEntity.USER_ROLES,
        entity_id=user.id,
        changes={"from": previous, "to": sorted(role.value for role in roles)},
    )
    await commit_or_conflict(session, "Roles could not be assigned.")
    return await get_user(session, principal, user_id)


async def delete_user(session: AsyncSession, principal: Principal, user_id: uuid.UUID) -> User:
    """Delete a user. Returns the deleted row so callers can audit it."""
    principal.require(Permission.USER_WRITE)
    user = await get_user(session, principal, user_id)
    if user.id == principal.user_id:
        raise ConflictError("You cannot delete your own account.")

    snapshot = {"email": user.email, "roles": sorted(row.name for row in user.roles)}
    await session.delete(user)
    await flush_or_conflict(session, "User could not be deleted.")
    await record_audit(
        session,
        principal,
        action=AuditAction.DELETE,
        entity_type=AuditEntity.USER,
        entity_id=user.id,
        changes=snapshot,
    )
    await commit_or_conflict(session, "User could not be deleted.")
    return user


async def list_roles(session: AsyncSession, principal: Principal) -> list[RoleRow]:
    """List the roles that can be assigned."""
    principal.require(Permission.USER_READ)
    stmt = select(RoleRow).order_by(RoleRow.name)
    return list((await session.execute(stmt)).scalars().all())


__all__ = [
    "create_user",
    "delete_user",
    "get_user",
    "list_roles",
    "list_users",
    "set_user_roles",
    "update_user",
]
