"""T2 PASS: user/role CRUD and RBAC enforcement at the route and service level."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from qe_auth import Permission, Role
from qe_database.models import Organisation, User
from tests.helpers import UserFactory, auth_header, make_user

pytestmark = pytest.mark.integration


def test_quality_engineer_cannot_call_an_administrator_only_endpoint(
    app_client: TestClient, as_user: UserFactory
) -> None:
    """The headline RBAC assertion: user:write is administrator-only."""
    _, qe_headers = as_user(Role.QUALITY_ENGINEER)

    resp = app_client.post(
        "/api/v1/users",
        headers=qe_headers,
        json={"email": f"new-{uuid.uuid4().hex}@example.com"},
    )

    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["error"]["code"] == "FORBIDDEN"
    assert Permission.USER_WRITE.value in body["error"]["message"]


def test_administrator_can_create_read_update_and_delete_a_user(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, admin = as_user(Role.ADMINISTRATOR)
    email = f"new-{uuid.uuid4().hex}@example.com"

    created = app_client.post(
        "/api/v1/users",
        headers=admin,
        json={"email": email, "full_name": "New Person", "roles": ["engineer"]},
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    assert created.json()["roles"] == ["engineer"]

    fetched = app_client.get(f"/api/v1/users/{user_id}", headers=admin)
    assert fetched.status_code == 200
    assert fetched.json()["email"] == email

    updated = app_client.patch(
        f"/api/v1/users/{user_id}", headers=admin, json={"full_name": "Renamed"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["full_name"] == "Renamed"
    assert updated.json()["is_active"] is True

    listed = app_client.get("/api/v1/users", headers=admin)
    assert listed.status_code == 200
    assert user_id in [item["id"] for item in listed.json()["items"]]
    assert listed.json()["total"] >= 2

    deleted = app_client.delete(f"/api/v1/users/{user_id}", headers=admin)
    assert deleted.status_code == 204, deleted.text
    assert app_client.get(f"/api/v1/users/{user_id}", headers=admin).status_code == 404


def test_duplicate_email_is_a_conflict(app_client: TestClient, as_user: UserFactory) -> None:
    _, admin = as_user(Role.ADMINISTRATOR)
    email = f"dup-{uuid.uuid4().hex}@example.com"

    assert app_client.post("/api/v1/users", headers=admin, json={"email": email}).status_code == 201
    clash = app_client.post("/api/v1/users", headers=admin, json={"email": email})

    assert clash.status_code == 409, clash.text
    assert clash.json()["error"]["code"] == "CONFLICT"


def test_role_assignment_requires_the_role_assign_permission(
    app_client: TestClient, as_user: UserFactory
) -> None:
    target, _ = as_user(Role.ENGINEER)
    _, lead = as_user(Role.QE_LEAD)

    resp = app_client.put(
        f"/api/v1/users/{target.id}/roles", headers=lead, json={"roles": ["qe_lead"]}
    )

    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_administrator_replaces_roles_and_the_change_takes_effect_immediately(
    app_client: TestClient, as_user: UserFactory
) -> None:
    target, target_headers = as_user(Role.ENGINEER)
    _, admin = as_user(Role.ADMINISTRATOR)

    assert app_client.get("/api/v1/users", headers=target_headers).status_code == 403

    promoted = app_client.put(
        f"/api/v1/users/{target.id}/roles", headers=admin, json={"roles": ["qe_lead"]}
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["roles"] == ["qe_lead"]

    # Same (unchanged) token — roles are re-read from the database each request.
    assert app_client.get("/api/v1/users", headers=target_headers).status_code == 200


def test_administrator_cannot_delete_or_demote_themselves(
    app_client: TestClient, as_user: UserFactory
) -> None:
    admin_user, admin = as_user(Role.ADMINISTRATOR)

    self_delete = app_client.delete(f"/api/v1/users/{admin_user.id}", headers=admin)
    assert self_delete.status_code == 409, self_delete.text

    self_demote = app_client.put(
        f"/api/v1/users/{admin_user.id}/roles", headers=admin, json={"roles": ["engineer"]}
    )
    assert self_demote.status_code == 409, self_demote.text


def test_users_are_scoped_to_the_callers_organisation(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    other_organisation: Organisation,
) -> None:
    _, admin = as_user(Role.ADMINISTRATOR)
    stranger = make_user(db, other_organisation, Role.ENGINEER)

    assert app_client.get(f"/api/v1/users/{stranger.id}", headers=admin).status_code == 404
    listed = app_client.get("/api/v1/users", headers=admin).json()
    assert str(stranger.id) not in [item["id"] for item in listed["items"]]

    # ...and a created user lands in the creator's organisation, not another.
    created = app_client.post(
        "/api/v1/users", headers=admin, json={"email": f"scoped-{uuid.uuid4().hex}@example.com"}
    )
    assert created.status_code == 201
    assert created.json()["organisation_id"] != str(other_organisation.id)


def test_deactivated_user_loses_api_access(app_client: TestClient, as_user: UserFactory) -> None:
    target, target_headers = as_user(Role.ENGINEER)
    _, admin = as_user(Role.ADMINISTRATOR)

    assert app_client.get("/api/v1/auth/me", headers=target_headers).status_code == 200

    resp = app_client.patch(f"/api/v1/users/{target.id}", headers=admin, json={"is_active": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_active"] is False
    assert app_client.get("/api/v1/auth/me", headers=target_headers).status_code == 401


def test_roles_endpoint_lists_the_five_platform_roles(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, admin = as_user(Role.ADMINISTRATOR)

    resp = app_client.get("/api/v1/roles", headers=admin)

    assert resp.status_code == 200, resp.text
    assert {row["name"] for row in resp.json()} == {role.value for role in Role}


def test_service_layer_enforces_permissions_without_the_router(
    db: Session, as_user: UserFactory
) -> None:
    """Defence in depth: a service called directly still refuses the action."""
    import asyncio

    from qe_api.services import users as user_service
    from qe_auth import Principal
    from qe_common.errors import ForbiddenError
    from qe_database.session import _async_session_factory

    engineer, _ = as_user(Role.ENGINEER)
    principal = Principal(
        user_id=engineer.id,
        organisation_id=engineer.organisation_id,
        email=engineer.email,
        roles=frozenset({Role.ENGINEER}),
    )

    async def _attempt() -> None:
        async with _async_session_factory()() as session:
            await user_service.create_user(
                session, principal, email="nope@example.com", full_name=None, roles=[]
            )

    with pytest.raises(ForbiddenError):
        asyncio.run(_attempt())

    # Nothing was written.
    assert db.execute(select(User).where(User.email == "nope@example.com")).first() is None


def test_unauthenticated_user_routes_are_401(app_client: TestClient) -> None:
    assert app_client.get("/api/v1/users").status_code == 401
    assert app_client.post("/api/v1/users", json={"email": "a@example.com"}).status_code == 401


def test_a_token_for_a_user_without_roles_has_no_permissions(
    app_client: TestClient, as_user: UserFactory
) -> None:
    roleless, _ = as_user()
    headers = auth_header(roleless)

    me = app_client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["permissions"] == []
    assert app_client.get("/api/v1/users", headers=headers).status_code == 403
