"""Request/response models for the v1 API.

Kept in one module so the wire contract for Phase 1 can be read end-to-end.
ORM objects are never returned directly; every response goes through a model
here, which is what keeps internal columns out of the API surface.
"""

from __future__ import annotations

import datetime as _dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from qe_auth import Permission, Role, parse_role
from qe_database.models import User

# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


class DevLoginRequest(BaseModel):
    """Dev-mode identity provider credential (ADR-0101): an email address."""

    email: EmailStr = Field(description="Address to sign in as.")


class UserRead(BaseModel):
    """A user as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organisation_id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    roles: list[Role] = Field(default_factory=list)
    created_at: _dt.datetime
    updated_at: _dt.datetime

    @classmethod
    def from_user(cls, user: User) -> UserRead:
        """Serialise a ``User`` whose ``roles`` relationship is already loaded."""
        roles = sorted(
            {role for role in (parse_role(row.name) for row in user.roles) if role is not None}
        )
        return cls(
            id=user.id,
            organisation_id=user.organisation_id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            roles=roles,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class TokenResponse(BaseModel):
    """OAuth-2-shaped bearer-token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds.")
    user: UserRead


class MeResponse(BaseModel):
    """The caller's identity plus its effective authorisation."""

    user: UserRead
    roles: list[Role]
    permissions: list[Permission]


__all__ = [
    "DevLoginRequest",
    "MeResponse",
    "TokenResponse",
    "UserRead",
]
