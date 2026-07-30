"""T3 PASS: organisation/project CRUD and cross-tenant data isolation."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from qe_auth import Role
from qe_database.models import Organisation, Project
from tests.helpers import UserFactory, auth_header, make_user

pytestmark = pytest.mark.integration


def _make_project(db: Session, organisation: Organisation, slug: str) -> Project:
    project = Project(organisation_id=organisation.id, name=slug.title(), slug=slug)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def test_a_user_cannot_read_another_tenants_project(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    organisation: Organisation,
    other_organisation: Organisation,
) -> None:
    """The headline isolation assertion: project B is invisible to tenant A."""
    project_a = _make_project(db, organisation, f"project-a-{uuid.uuid4().hex[:8]}")
    project_b = _make_project(db, other_organisation, f"project-b-{uuid.uuid4().hex[:8]}")
    _, headers_a = as_user(Role.QE_LEAD)

    own = app_client.get(f"/api/v1/projects/{project_a.id}", headers=headers_a)
    assert own.status_code == 200, own.text
    assert own.json()["slug"] == project_a.slug

    foreign = app_client.get(f"/api/v1/projects/{project_b.id}", headers=headers_a)
    assert foreign.status_code == 404, foreign.text
    assert foreign.json()["error"]["code"] == "NOT_FOUND"

    listed = app_client.get("/api/v1/projects", headers=headers_a).json()
    slugs = {item["slug"] for item in listed["items"]}
    assert project_a.slug in slugs
    assert project_b.slug not in slugs


def test_isolation_holds_for_writes_too(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    other_organisation: Organisation,
) -> None:
    project_b = _make_project(db, other_organisation, f"project-b-{uuid.uuid4().hex[:8]}")
    _, headers_a = as_user(Role.QE_LEAD)

    patched = app_client.patch(
        f"/api/v1/projects/{project_b.id}", headers=headers_a, json={"name": "Hijacked"}
    )
    assert patched.status_code == 404, patched.text

    removed = app_client.delete(f"/api/v1/projects/{project_b.id}", headers=headers_a)
    assert removed.status_code == 404, removed.text

    db.refresh(project_b)
    assert project_b.name != "Hijacked"


def test_project_crud_round_trip(app_client: TestClient, as_user: UserFactory) -> None:
    _, lead = as_user(Role.QE_LEAD)

    created = app_client.post(
        "/api/v1/projects",
        headers=lead,
        json={"name": "Payments Platform", "description": "Checkout services"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    project_id = body["id"]
    assert body["slug"] == "payments-platform"
    assert body["description"] == "Checkout services"

    fetched = app_client.get(f"/api/v1/projects/{project_id}", headers=lead)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Payments Platform"

    updated = app_client.patch(
        f"/api/v1/projects/{project_id}", headers=lead, json={"name": "Payments"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Payments"
    assert updated.json()["slug"] == "payments-platform", "slug is immutable"

    listed = app_client.get("/api/v1/projects", headers=lead)
    assert listed.status_code == 200
    assert project_id in [item["id"] for item in listed.json()["items"]]

    deleted = app_client.delete(f"/api/v1/projects/{project_id}", headers=lead)
    assert deleted.status_code == 204, deleted.text
    assert app_client.get(f"/api/v1/projects/{project_id}", headers=lead).status_code == 404


def test_duplicate_project_slug_in_one_tenant_is_a_conflict(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, lead = as_user(Role.QE_LEAD)
    payload = {"name": f"Dup {uuid.uuid4().hex[:8]}"}

    assert app_client.post("/api/v1/projects", headers=lead, json=payload).status_code == 201
    clash = app_client.post("/api/v1/projects", headers=lead, json=payload)

    assert clash.status_code == 409, clash.text
    assert clash.json()["error"]["code"] == "CONFLICT"


def test_the_same_slug_is_free_in_a_different_tenant(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    other_organisation: Organisation,
) -> None:
    """Project slugs are unique per organisation, not globally."""
    shared_slug = f"shared-{uuid.uuid4().hex[:8]}"
    _make_project(db, other_organisation, shared_slug)
    _, lead = as_user(Role.QE_LEAD)

    created = app_client.post(
        "/api/v1/projects", headers=lead, json={"name": "Shared", "slug": shared_slug}
    )

    assert created.status_code == 201, created.text
    assert created.json()["slug"] == shared_slug


def test_engineers_can_read_projects_but_not_write_them(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, engineer = as_user(Role.ENGINEER)

    assert app_client.get("/api/v1/projects", headers=engineer).status_code == 200
    denied = app_client.post("/api/v1/projects", headers=engineer, json={"name": "Nope"})
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "FORBIDDEN"


def test_project_routes_require_authentication(app_client: TestClient) -> None:
    assert app_client.get("/api/v1/projects").status_code == 401
    assert app_client.post("/api/v1/projects", json={"name": "x"}).status_code == 401


def test_a_name_with_no_slug_characters_is_rejected(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, lead = as_user(Role.QE_LEAD)
    resp = app_client.post("/api/v1/projects", headers=lead, json={"name": "///"})
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_organisation_reads_are_limited_to_the_callers_own(
    app_client: TestClient,
    as_user: UserFactory,
    organisation: Organisation,
    other_organisation: Organisation,
) -> None:
    _, engineer = as_user(Role.ENGINEER)

    listed = app_client.get("/api/v1/organisations", headers=engineer)
    assert listed.status_code == 200, listed.text
    assert [row["id"] for row in listed.json()] == [str(organisation.id)]

    own = app_client.get(f"/api/v1/organisations/{organisation.id}", headers=engineer)
    assert own.status_code == 200
    assert own.json()["slug"] == organisation.slug

    foreign = app_client.get(f"/api/v1/organisations/{other_organisation.id}", headers=engineer)
    assert foreign.status_code == 404, foreign.text


def test_only_administrators_can_rename_an_organisation(
    app_client: TestClient, as_user: UserFactory, organisation: Organisation
) -> None:
    _, lead = as_user(Role.QE_LEAD)
    _, admin = as_user(Role.ADMINISTRATOR)

    denied = app_client.patch(
        f"/api/v1/organisations/{organisation.id}", headers=lead, json={"name": "Renamed"}
    )
    assert denied.status_code == 403, denied.text

    allowed = app_client.patch(
        f"/api/v1/organisations/{organisation.id}", headers=admin, json={"name": "Renamed"}
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["name"] == "Renamed"
    assert allowed.json()["slug"] == organisation.slug, "slug is immutable"


def test_a_user_in_another_tenant_sees_only_their_own_projects(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    organisation: Organisation,
    other_organisation: Organisation,
) -> None:
    """Symmetry check: isolation is not one-directional."""
    _make_project(db, organisation, f"a-{uuid.uuid4().hex[:8]}")
    project_b = _make_project(db, other_organisation, f"b-{uuid.uuid4().hex[:8]}")
    stranger = make_user(db, other_organisation, Role.QE_LEAD)
    headers_b = auth_header(stranger, (Role.QE_LEAD,))

    listed = app_client.get("/api/v1/projects", headers=headers_b).json()

    assert [item["id"] for item in listed["items"]] == [str(project_b.id)]
    assert listed["total"] == 1
