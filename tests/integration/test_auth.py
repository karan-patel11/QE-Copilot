"""T1 PASS: protected routes reject unauthenticated callers and accept authenticated ones."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from qe_auth import Role, issue_token
from qe_database.models import User
from tests.helpers import UserFactory, auth_header

pytestmark = pytest.mark.integration

PROTECTED = "/api/v1/auth/me"


def test_unauthenticated_request_is_401(app_client: TestClient) -> None:
    resp = app_client.get(PROTECTED)

    assert resp.status_code == 401, resp.text
    body = resp.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert set(body["error"]) == {"code", "message", "request_id", "details"}


def test_authenticated_request_succeeds(app_client: TestClient, as_user: UserFactory) -> None:
    user, headers = as_user(Role.QUALITY_ENGINEER)

    resp = app_client.get(PROTECTED, headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["email"] == user.email
    assert body["roles"] == ["quality_engineer"]
    assert "repository:write" in body["permissions"]
    assert "user:write" not in body["permissions"]


def test_malformed_bearer_token_is_401(app_client: TestClient) -> None:
    resp = app_client.get(PROTECTED, headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401, resp.text
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_token_for_unknown_user_is_401(app_client: TestClient) -> None:
    """A validly signed token whose subject no longer exists must not authenticate."""
    token, _ = issue_token(
        user_id=uuid.uuid4(),
        organisation_id=uuid.uuid4(),
        email="ghost@example.com",
        roles=frozenset({Role.ADMINISTRATOR}),
    )
    resp = app_client.get(PROTECTED, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401, resp.text


def test_deactivated_user_is_401(app_client: TestClient, db: Session, as_user: UserFactory) -> None:
    user, headers = as_user(Role.ENGINEER)
    assert app_client.get(PROTECTED, headers=headers).status_code == 200

    user.is_active = False
    db.add(user)
    db.commit()

    assert app_client.get(PROTECTED, headers=headers).status_code == 401


def test_roles_are_resolved_from_the_database_not_the_token(
    app_client: TestClient, as_user: UserFactory
) -> None:
    """A forged roles claim grants nothing: authorisation comes from user_roles."""
    user, _ = as_user(Role.ENGINEER)
    inflated = auth_header(user, (Role.ADMINISTRATOR,))

    body = app_client.get(PROTECTED, headers=inflated).json()

    assert body["roles"] == ["engineer"]
    assert "user:write" not in body["permissions"]


def test_dev_login_provisions_and_authenticates(app_client: TestClient, db: Session) -> None:
    email = f"dev-{uuid.uuid4().hex[:12]}@example.com"
    try:
        resp = app_client.post("/api/v1/auth/dev/login", json={"email": email})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0
        assert body["user"]["email"] == email
        assert body["user"]["roles"] == ["engineer"]

        me = app_client.get(PROTECTED, headers={"Authorization": f"Bearer {body['access_token']}"})
        assert me.status_code == 200, me.text
        assert me.json()["user"]["email"] == email
    finally:
        db.execute(delete(User).where(User.email == email))
        db.commit()


def test_dev_login_rejects_a_malformed_email(app_client: TestClient) -> None:
    resp = app_client.post("/api/v1/auth/dev/login", json={"email": "not-an-email"})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
