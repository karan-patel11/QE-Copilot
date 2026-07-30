"""The authenticated caller and its authorisation checks."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from functools import cached_property

from qe_auth.roles import Permission, Role, permissions_for
from qe_common.errors import ForbiddenError


@dataclass(frozen=True)
class Principal:
    """An authenticated caller resolved from a request.

    ``organisation_id`` is the tenant boundary: every query a request makes is
    filtered by it (ADR-0106).
    """

    user_id: uuid.UUID
    organisation_id: uuid.UUID
    email: str
    roles: frozenset[Role] = field(default_factory=frozenset)

    @cached_property
    def permissions(self) -> frozenset[Permission]:
        """Every permission this principal holds, via its roles."""
        return permissions_for(self.roles)

    def has_role(self, role: Role) -> bool:
        return role in self.roles

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.permissions

    def require(self, *permissions: Permission) -> None:
        """Raise :class:`ForbiddenError` unless every permission is held.

        Called by route guards *and* directly by service functions, so a service
        reached from a script or worker is protected too.
        """
        missing = [p for p in permissions if p not in self.permissions]
        if missing:
            raise ForbiddenError(
                "Insufficient permissions: " + ", ".join(sorted(p.value for p in missing))
            )


__all__ = ["Principal"]
