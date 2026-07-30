"""Authentication routes: dev-mode sign-in and caller introspection."""

from __future__ import annotations

from fastapi import APIRouter, status

from qe_api.dependencies import PrincipalDep, SessionDep
from qe_api.schemas import DevLoginRequest, MeResponse, TokenResponse, UserRead
from qe_api.services import auth as auth_service
from qe_auth import issue_token

router = APIRouter(prefix="/auth", tags=["auth"])

# Mounted only when AUTH_DEV_MODE is enabled (see qe_api.routers.v1).
dev_router = APIRouter(prefix="/auth/dev", tags=["auth"])


@dev_router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Sign in via the dev-mode identity provider",
)
async def dev_login(payload: DevLoginRequest, session: SessionDep) -> TokenResponse:
    """Exchange an email address for a platform access token (ADR-0101).

    Development only: production boots with ``AUTH_DEV_MODE=false``, which both
    unmounts this route and is enforced by ``Settings`` validation.
    """
    user = await auth_service.dev_login(session, str(payload.email))
    user_read = UserRead.from_user(user)
    token, expires_in = issue_token(
        user_id=user.id,
        organisation_id=user.organisation_id,
        email=user.email,
        roles=frozenset(user_read.roles),
    )
    return TokenResponse(access_token=token, expires_in=expires_in, user=user_read)


@router.get("/me", response_model=MeResponse, summary="Describe the authenticated caller")
async def me(principal: PrincipalDep, session: SessionDep) -> MeResponse:
    """Return the caller's user record, roles, and effective permissions."""
    user = await auth_service.load_user(session, principal.user_id)
    user_read = UserRead.from_user(user)
    return MeResponse(
        user=user_read,
        roles=user_read.roles,
        permissions=sorted(principal.permissions),
    )


__all__ = ["dev_router", "router"]
