"""Shared FastAPI dependencies: database session, principal resolution, guards."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from qe_auth import Permission, Principal, decode_token, parse_role
from qe_common.errors import UnauthorizedError
from qe_database.models import User
from qe_database.session import get_async_session
from qe_observability import bind_log_context

# ``auto_error=False`` so a missing header raises our own envelope-shaped
# UnauthorizedError instead of Starlette's bare 403.
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth")

SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


async def get_principal(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> Principal:
    """Resolve the bearer token to a :class:`Principal`.

    The token authenticates; the *database* authorises. Roles are re-read from
    ``user_roles`` on every request so revoking a role takes effect immediately
    rather than when the token expires.
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Authentication required.")

    claims = decode_token(credentials.credentials)
    user = await session.get(User, claims.user_id, options=[selectinload(User.roles)])
    if user is None or not user.is_active:
        raise UnauthorizedError("Access token does not identify an active user.")

    roles = frozenset(role for role in (parse_role(r.name) for r in user.roles) if role is not None)
    principal = Principal(
        user_id=user.id,
        organisation_id=user.organisation_id,
        email=user.email,
        roles=roles,
    )
    bind_log_context(user_id=str(principal.user_id))
    return principal


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def require(*permissions: Permission) -> Callable[[Principal], Awaitable[Principal]]:
    """Build a dependency asserting the caller holds every listed permission.

    Guards name permissions, never roles (ADR-0105), so policy lives entirely in
    ``ROLE_PERMISSIONS``.
    """

    async def _guard(principal: PrincipalDep) -> Principal:
        principal.require(*permissions)
        return principal

    return _guard


__all__ = [
    "PrincipalDep",
    "SessionDep",
    "bearer_scheme",
    "get_principal",
    "require",
]
