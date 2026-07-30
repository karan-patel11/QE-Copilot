"""Authentication & authorization primitives.

Phase 1 implements the design's identity model: signed access tokens
(:mod:`qe_auth.tokens`), an authenticated :class:`~qe_auth.principal.Principal`,
and the role → permission matrix (:mod:`qe_auth.roles`) that every route guard
and service-level check consults.
"""

from __future__ import annotations

from qe_auth.principal import Principal
from qe_auth.roles import (
    ROLE_DESCRIPTIONS,
    ROLE_PERMISSIONS,
    Permission,
    Role,
    parse_role,
    permissions_for,
)
from qe_auth.tokens import ALGORITHM, TokenClaims, decode_token, issue_token

__all__ = [
    "ALGORITHM",
    "ROLE_DESCRIPTIONS",
    "ROLE_PERMISSIONS",
    "Permission",
    "Principal",
    "Role",
    "TokenClaims",
    "decode_token",
    "issue_token",
    "parse_role",
    "permissions_for",
]
