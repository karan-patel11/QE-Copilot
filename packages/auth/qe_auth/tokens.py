"""Platform access tokens (ADR-0102).

Short-lived HS256 JWTs signed with ``AUTH_SECRET_KEY``. Issuance belongs to the
identity provider (Phase 1: the dev-mode provider); verification is
provider-agnostic, so swapping in an external OIDC issuer means replacing
:func:`decode_token` alone — route guards are untouched.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass
from typing import Any

import jwt

from qe_auth.roles import Role, parse_role
from qe_common.config import Settings, get_settings
from qe_common.errors import UnauthorizedError

ALGORITHM = "HS256"


@dataclass(frozen=True)
class TokenClaims:
    """The subset of claims the platform relies on."""

    user_id: uuid.UUID
    organisation_id: uuid.UUID
    email: str
    roles: frozenset[Role]
    expires_at: _dt.datetime


def issue_token(
    *,
    user_id: uuid.UUID,
    organisation_id: uuid.UUID,
    email: str,
    roles: frozenset[Role],
    settings: Settings | None = None,
) -> tuple[str, int]:
    """Mint a signed access token; returns ``(token, expires_in_seconds)``."""
    resolved = settings or get_settings()
    now = _dt.datetime.now(_dt.UTC)
    ttl = resolved.auth_token_ttl_seconds
    payload: dict[str, Any] = {
        "iss": resolved.auth_issuer,
        "aud": resolved.auth_audience,
        "sub": str(user_id),
        "org": str(organisation_id),
        "email": email,
        # Advisory only: the server re-resolves roles from the database on every
        # request so a revoked role takes effect before the token expires.
        "roles": sorted(role.value for role in roles),
        "iat": int(now.timestamp()),
        "exp": int((now + _dt.timedelta(seconds=ttl)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, resolved.auth_secret_key, algorithm=ALGORITHM)
    return token, ttl


def decode_token(token: str, settings: Settings | None = None) -> TokenClaims:
    """Verify ``token`` and return its claims.

    Raises :class:`UnauthorizedError` for any failure — expired, wrong audience
    or issuer, bad signature, or a malformed payload — so callers never have to
    distinguish library exception types.
    """
    resolved = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            resolved.auth_secret_key,
            algorithms=[ALGORITHM],
            audience=resolved.auth_audience,
            issuer=resolved.auth_issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Access token is invalid.") from exc

    try:
        user_id = uuid.UUID(str(payload["sub"]))
        organisation_id = uuid.UUID(str(payload["org"]))
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Access token is missing a valid subject.") from exc

    raw_roles = payload.get("roles") or []
    roles = frozenset(
        role for role in (parse_role(str(name)) for name in raw_roles) if role is not None
    )
    return TokenClaims(
        user_id=user_id,
        organisation_id=organisation_id,
        email=str(payload.get("email", "")),
        roles=roles,
        expires_at=_dt.datetime.fromtimestamp(int(payload["exp"]), tz=_dt.UTC),
    )


__all__ = ["ALGORITHM", "TokenClaims", "decode_token", "issue_token"]
