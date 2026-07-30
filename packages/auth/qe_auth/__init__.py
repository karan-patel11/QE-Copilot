"""Authentication & authorization primitives.

Phase 0 ships type-level stubs and the role model only. Real token verification,
session handling, and RBAC enforcement arrive in a later phase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    """Baseline platform roles (mirrors the ``roles`` table seed)."""

    ADMIN = "admin"
    MAINTAINER = "maintainer"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"


@dataclass(frozen=True)
class Principal:
    """An authenticated caller resolved from a request."""

    user_id: str
    organisation_id: str
    roles: frozenset[Role] = field(default_factory=frozenset)

    def has_role(self, role: Role) -> bool:
        return role in self.roles


def verify_token(token: str) -> Principal:
    """Resolve a bearer token to a :class:`Principal`.

    TODO(phase-1): implement real JWT/session verification against the users and
    user_roles tables. Phase 0 intentionally raises so nothing depends on a fake
    identity.
    """
    raise NotImplementedError("auth verification is implemented in a later phase")


__all__ = ["Principal", "Role", "verify_token"]
