"""T1/T2 unit: token issue/verify semantics and the permission matrix."""

from __future__ import annotations

import datetime as _dt
import uuid

import jwt
import pytest

from qe_auth import (
    ROLE_PERMISSIONS,
    Permission,
    Principal,
    Role,
    decode_token,
    issue_token,
    parse_role,
    permissions_for,
)
from qe_common.config import Settings
from qe_common.errors import ForbiddenError, UnauthorizedError

SETTINGS = Settings(
    AUTH_SECRET_KEY="unit-test-key",
    AUTH_ISSUER="qe-copilot",
    AUTH_AUDIENCE="qe-copilot-api",
    AUTH_TOKEN_TTL_SECONDS=60,
)


def test_token_round_trips() -> None:
    user_id, org_id = uuid.uuid4(), uuid.uuid4()
    token, expires_in = issue_token(
        user_id=user_id,
        organisation_id=org_id,
        email="dev@example.com",
        roles=frozenset({Role.QE_LEAD}),
        settings=SETTINGS,
    )
    claims = decode_token(token, SETTINGS)

    assert expires_in == 60
    assert claims.user_id == user_id
    assert claims.organisation_id == org_id
    assert claims.email == "dev@example.com"
    assert claims.roles == frozenset({Role.QE_LEAD})
    assert claims.expires_at > _dt.datetime.now(_dt.UTC)


def test_expired_token_rejected() -> None:
    expired = jwt.encode(
        {
            "iss": SETTINGS.auth_issuer,
            "aud": SETTINGS.auth_audience,
            "sub": str(uuid.uuid4()),
            "org": str(uuid.uuid4()),
            "iat": 1_600_000_000,
            "exp": 1_600_000_060,
        },
        SETTINGS.auth_secret_key,
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError, match="expired"):
        decode_token(expired, SETTINGS)


def test_token_signed_with_another_key_rejected() -> None:
    token, _ = issue_token(
        user_id=uuid.uuid4(),
        organisation_id=uuid.uuid4(),
        email="dev@example.com",
        roles=frozenset(),
        settings=SETTINGS,
    )
    other = Settings(AUTH_SECRET_KEY="a-different-key")
    with pytest.raises(UnauthorizedError, match="invalid"):
        decode_token(token, other)


def test_token_for_another_audience_rejected() -> None:
    token, _ = issue_token(
        user_id=uuid.uuid4(),
        organisation_id=uuid.uuid4(),
        email="dev@example.com",
        roles=frozenset(),
        settings=Settings(AUTH_SECRET_KEY="unit-test-key", AUTH_AUDIENCE="someone-else"),
    )
    with pytest.raises(UnauthorizedError):
        decode_token(token, SETTINGS)


def test_garbage_token_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        decode_token("not-a-jwt", SETTINGS)


def test_unknown_role_claims_are_ignored_not_fatal() -> None:
    token = jwt.encode(
        {
            "iss": SETTINGS.auth_issuer,
            "aud": SETTINGS.auth_audience,
            "sub": str(uuid.uuid4()),
            "org": str(uuid.uuid4()),
            "roles": ["engineer", "wizard"],
            "iat": int(_dt.datetime.now(_dt.UTC).timestamp()),
            "exp": int(_dt.datetime.now(_dt.UTC).timestamp()) + 60,
        },
        SETTINGS.auth_secret_key,
        algorithm="HS256",
    )
    assert decode_token(token, SETTINGS).roles == frozenset({Role.ENGINEER})


def test_parse_role() -> None:
    assert parse_role("qe_lead") is Role.QE_LEAD
    assert parse_role("wizard") is None


def test_administrator_holds_every_permission() -> None:
    assert ROLE_PERMISSIONS[Role.ADMINISTRATOR] == frozenset(Permission)


def test_quality_engineer_cannot_write_users() -> None:
    granted = permissions_for([Role.QUALITY_ENGINEER])
    assert Permission.USER_WRITE not in granted
    assert Permission.ROLE_ASSIGN not in granted
    assert Permission.REPOSITORY_WRITE in granted


def test_permissions_are_the_union_of_roles() -> None:
    assert permissions_for([Role.ENGINEER, Role.QE_LEAD]) == permissions_for([Role.QE_LEAD])
    assert permissions_for([]) == frozenset()


def test_principal_require_raises_forbidden_with_missing_permissions() -> None:
    principal = Principal(
        user_id=uuid.uuid4(),
        organisation_id=uuid.uuid4(),
        email="qe@example.com",
        roles=frozenset({Role.QUALITY_ENGINEER}),
    )
    principal.require(Permission.REPOSITORY_WRITE)
    with pytest.raises(ForbiddenError, match="user:write"):
        principal.require(Permission.USER_WRITE)
