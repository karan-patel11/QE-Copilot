"""T4 PASS: repository CRUD, the project foreign key, and tenancy through it."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from qe_auth import Role
from qe_database.models import Organisation, Project, Repository
from tests.helpers import UserFactory

pytestmark = pytest.mark.integration


def _make_project(db: Session, organisation: Organisation) -> Project:
    slug = f"proj-{uuid.uuid4().hex[:8]}"
    project = Project(organisation_id=organisation.id, name=slug.title(), slug=slug)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def test_repository_crud_round_trip(
    app_client: TestClient, db: Session, as_user: UserFactory, organisation: Organisation
) -> None:
    project = _make_project(db, organisation)
    _, qe = as_user(Role.QUALITY_ENGINEER)
    base = f"/api/v1/projects/{project.id}/repositories"

    created = app_client.post(
        base,
        headers=qe,
        json={
            "name": "checkout-service",
            "url": "https://github.com/acme/checkout-service",
            "provider": "github",
            "default_branch": "develop",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    repo_id = body["id"]
    assert body["project_id"] == str(project.id)
    assert body["default_branch"] == "develop"

    fetched = app_client.get(f"/api/v1/repositories/{repo_id}", headers=qe)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "checkout-service"

    updated = app_client.patch(
        f"/api/v1/repositories/{repo_id}",
        headers=qe,
        json={"name": "checkout", "default_branch": "main"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "checkout"
    assert updated.json()["default_branch"] == "main"

    listed = app_client.get(base, headers=qe)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [repo_id]
    assert listed.json()["total"] == 1

    deleted = app_client.delete(f"/api/v1/repositories/{repo_id}", headers=qe)
    assert deleted.status_code == 204, deleted.text
    assert app_client.get(f"/api/v1/repositories/{repo_id}", headers=qe).status_code == 404
    assert db.execute(select(Repository).where(Repository.id == repo_id)).first() is None


def test_creating_under_an_unknown_project_is_404_and_writes_nothing(
    app_client: TestClient, db: Session, as_user: UserFactory
) -> None:
    """The project foreign key can never be forged: the parent is checked first."""
    _, qe = as_user(Role.QUALITY_ENGINEER)
    ghost = uuid.uuid4()

    resp = app_client.post(
        f"/api/v1/projects/{ghost}/repositories",
        headers=qe,
        json={"name": "x", "url": "https://github.com/acme/x"},
    )

    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "NOT_FOUND"
    assert db.execute(select(Repository).where(Repository.project_id == ghost)).first() is None


def test_creating_under_another_tenants_project_is_404(
    app_client: TestClient, db: Session, as_user: UserFactory, other_organisation: Organisation
) -> None:
    foreign_project = _make_project(db, other_organisation)
    _, qe = as_user(Role.QUALITY_ENGINEER)

    resp = app_client.post(
        f"/api/v1/projects/{foreign_project.id}/repositories",
        headers=qe,
        json={"name": "x", "url": "https://github.com/acme/x"},
    )

    assert resp.status_code == 404, resp.text
    assert (
        db.execute(select(Repository).where(Repository.project_id == foreign_project.id)).first()
        is None
    )


def test_another_tenants_repository_is_invisible(
    app_client: TestClient, db: Session, as_user: UserFactory, other_organisation: Organisation
) -> None:
    foreign_project = _make_project(db, other_organisation)
    foreign_repo = Repository(
        project_id=foreign_project.id, name="secret", url="https://github.com/acme/secret"
    )
    db.add(foreign_repo)
    db.commit()
    db.refresh(foreign_repo)
    _, qe = as_user(Role.QUALITY_ENGINEER)

    assert app_client.get(f"/api/v1/repositories/{foreign_repo.id}", headers=qe).status_code == 404
    assert (
        app_client.patch(
            f"/api/v1/repositories/{foreign_repo.id}", headers=qe, json={"name": "hijack"}
        ).status_code
        == 404
    )
    assert (
        app_client.delete(f"/api/v1/repositories/{foreign_repo.id}", headers=qe).status_code == 404
    )
    assert (
        app_client.get(
            f"/api/v1/projects/{foreign_project.id}/repositories", headers=qe
        ).status_code
        == 404
    )

    db.refresh(foreign_repo)
    assert foreign_repo.name == "secret"


def test_the_same_url_cannot_be_registered_twice_on_one_project(
    app_client: TestClient, db: Session, as_user: UserFactory, organisation: Organisation
) -> None:
    project = _make_project(db, organisation)
    _, qe = as_user(Role.QUALITY_ENGINEER)
    payload = {"name": "dup", "url": "https://github.com/acme/dup"}
    base = f"/api/v1/projects/{project.id}/repositories"

    assert app_client.post(base, headers=qe, json=payload).status_code == 201
    clash = app_client.post(base, headers=qe, json=payload)

    assert clash.status_code == 409, clash.text
    assert clash.json()["error"]["code"] == "CONFLICT"


def test_the_same_url_is_free_on_a_different_project(
    app_client: TestClient, db: Session, as_user: UserFactory, organisation: Organisation
) -> None:
    """Uniqueness is (project_id, url), not url alone."""
    first, second = _make_project(db, organisation), _make_project(db, organisation)
    _, qe = as_user(Role.QUALITY_ENGINEER)
    payload = {"name": "shared", "url": "https://github.com/acme/shared"}

    assert (
        app_client.post(
            f"/api/v1/projects/{first.id}/repositories", headers=qe, json=payload
        ).status_code
        == 201
    )
    assert (
        app_client.post(
            f"/api/v1/projects/{second.id}/repositories", headers=qe, json=payload
        ).status_code
        == 201
    )


def test_deleting_a_project_cascades_to_its_repositories(
    app_client: TestClient, db: Session, as_user: UserFactory, organisation: Organisation
) -> None:
    project = _make_project(db, organisation)
    _, lead = as_user(Role.QE_LEAD)
    created = app_client.post(
        f"/api/v1/projects/{project.id}/repositories",
        headers=lead,
        json={"name": "cascade", "url": "https://github.com/acme/cascade"},
    )
    assert created.status_code == 201, created.text
    repo_id = uuid.UUID(created.json()["id"])

    assert app_client.delete(f"/api/v1/projects/{project.id}", headers=lead).status_code == 204

    assert db.execute(select(Repository).where(Repository.id == repo_id)).first() is None


def test_engineers_may_read_repositories_but_not_write_them(
    app_client: TestClient, db: Session, as_user: UserFactory, organisation: Organisation
) -> None:
    project = _make_project(db, organisation)
    _, engineer = as_user(Role.ENGINEER)
    base = f"/api/v1/projects/{project.id}/repositories"

    assert app_client.get(base, headers=engineer).status_code == 200
    denied = app_client.post(
        base, headers=engineer, json={"name": "x", "url": "https://github.com/acme/x"}
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "FORBIDDEN"


def test_an_unsupported_provider_is_rejected(
    app_client: TestClient, db: Session, as_user: UserFactory, organisation: Organisation
) -> None:
    project = _make_project(db, organisation)
    _, qe = as_user(Role.QUALITY_ENGINEER)

    resp = app_client.post(
        f"/api/v1/projects/{project.id}/repositories",
        headers=qe,
        json={"name": "x", "url": "https://example.com/x", "provider": "carrier-pigeon"},
    )

    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_repository_routes_require_authentication(
    app_client: TestClient, db: Session, organisation: Organisation
) -> None:
    project = _make_project(db, organisation)
    assert app_client.get(f"/api/v1/projects/{project.id}/repositories").status_code == 401
    assert app_client.get(f"/api/v1/repositories/{uuid.uuid4()}").status_code == 401
