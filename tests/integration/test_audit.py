"""T6 PASS: every mutating action across T2-T5 writes an audit row.

Each case performs a real mutation through the API and then asserts the row
exists with the right actor, action, and entity — read from the database, not
from the audit endpoint, so the assertion does not depend on the read API.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from qe_auth import Role
from qe_common.audit import AuditAction, AuditEntity
from qe_database.models import AuditLog, Organisation, Project, User
from tests.helpers import UserFactory

pytestmark = pytest.mark.integration


def _audit_rows(
    db: Session, entity_type: AuditEntity, entity_id: uuid.UUID | str
) -> list[AuditLog]:
    stmt = (
        select(AuditLog)
        .where(
            AuditLog.entity_type == entity_type.value,
            AuditLog.entity_id == uuid.UUID(str(entity_id)),
        )
        .order_by(AuditLog.created_at)
    )
    return list(db.execute(stmt).scalars().all())


def _make_project(db: Session, organisation: Organisation) -> Project:
    slug = f"aud-{uuid.uuid4().hex[:8]}"
    project = Project(organisation_id=organisation.id, name=slug.title(), slug=slug)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def test_creating_a_user_is_audited_with_actor_action_and_entity(
    app_client: TestClient, db: Session, as_user: UserFactory
) -> None:
    """The headline audit assertion."""
    admin_user, admin = as_user(Role.ADMINISTRATOR)
    email = f"audited-{uuid.uuid4().hex}@example.com"

    created = app_client.post("/api/v1/users", headers=admin, json={"email": email})
    assert created.status_code == 201, created.text

    rows = _audit_rows(db, AuditEntity.USER, created.json()["id"])
    assert len(rows) == 1
    entry = rows[0]
    assert entry.action == AuditAction.CREATE.value
    assert entry.entity_type == AuditEntity.USER.value
    assert entry.actor_user_id == admin_user.id
    assert entry.actor_email == admin_user.email
    assert entry.organisation_id == admin_user.organisation_id
    assert entry.request_id, "the correlation id is captured"
    assert entry.changes == {"email": email, "roles": []}
    assert entry.created_at is not None


def test_update_delete_and_role_assignment_are_each_audited(
    app_client: TestClient, db: Session, as_user: UserFactory
) -> None:
    _, admin = as_user(Role.ADMINISTRATOR)
    created = app_client.post(
        "/api/v1/users", headers=admin, json={"email": f"u-{uuid.uuid4().hex}@example.com"}
    )
    user_id = created.json()["id"]

    assert (
        app_client.patch(
            f"/api/v1/users/{user_id}", headers=admin, json={"full_name": "Renamed"}
        ).status_code
        == 200
    )
    assert (
        app_client.put(
            f"/api/v1/users/{user_id}/roles", headers=admin, json={"roles": ["qe_lead"]}
        ).status_code
        == 200
    )
    assert app_client.delete(f"/api/v1/users/{user_id}", headers=admin).status_code == 204

    actions = [row.action for row in _audit_rows(db, AuditEntity.USER, user_id)]
    assert actions == [AuditAction.CREATE.value, AuditAction.UPDATE.value, AuditAction.DELETE.value]

    role_rows = _audit_rows(db, AuditEntity.USER_ROLES, user_id)
    assert len(role_rows) == 1
    assert role_rows[0].changes == {"from": [], "to": ["qe_lead"]}


def test_the_audit_row_survives_the_entity_it_describes(
    app_client: TestClient, db: Session, as_user: UserFactory
) -> None:
    """entity_id is not a foreign key, so deletion history is not self-erasing."""
    _, admin = as_user(Role.ADMINISTRATOR)
    email = f"gone-{uuid.uuid4().hex}@example.com"
    user_id = app_client.post("/api/v1/users", headers=admin, json={"email": email}).json()["id"]
    assert app_client.delete(f"/api/v1/users/{user_id}", headers=admin).status_code == 204

    assert db.execute(select(User).where(User.id == uuid.UUID(user_id))).first() is None
    delete_row = _audit_rows(db, AuditEntity.USER, user_id)[-1]
    assert delete_row.action == AuditAction.DELETE.value
    assert delete_row.changes == {"email": email, "roles": []}


def test_project_mutations_are_audited(
    app_client: TestClient, db: Session, as_user: UserFactory
) -> None:
    _, lead = as_user(Role.QE_LEAD)
    created = app_client.post(
        "/api/v1/projects", headers=lead, json={"name": f"Audited {uuid.uuid4().hex[:6]}"}
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]

    app_client.patch(f"/api/v1/projects/{project_id}", headers=lead, json={"name": "Renamed"})
    app_client.delete(f"/api/v1/projects/{project_id}", headers=lead)

    actions = [row.action for row in _audit_rows(db, AuditEntity.PROJECT, project_id)]
    assert actions == [AuditAction.CREATE.value, AuditAction.UPDATE.value, AuditAction.DELETE.value]


def test_repository_mutations_are_audited(
    app_client: TestClient, db: Session, as_user: UserFactory, organisation: Organisation
) -> None:
    project = _make_project(db, organisation)
    _, qe = as_user(Role.QUALITY_ENGINEER)
    created = app_client.post(
        f"/api/v1/projects/{project.id}/repositories",
        headers=qe,
        json={"name": "audited", "url": f"https://github.com/acme/{uuid.uuid4().hex[:8]}"},
    )
    assert created.status_code == 201, created.text
    repo_id = created.json()["id"]

    app_client.patch(f"/api/v1/repositories/{repo_id}", headers=qe, json={"name": "renamed"})
    app_client.delete(f"/api/v1/repositories/{repo_id}", headers=qe)

    rows = _audit_rows(db, AuditEntity.REPOSITORY, repo_id)
    assert [row.action for row in rows] == [
        AuditAction.CREATE.value,
        AuditAction.UPDATE.value,
        AuditAction.DELETE.value,
    ]
    assert rows[1].changes == {"name": {"from": "audited", "to": "renamed"}}


def test_organisation_rename_is_audited(
    app_client: TestClient, db: Session, as_user: UserFactory, organisation: Organisation
) -> None:
    _, admin = as_user(Role.ADMINISTRATOR)

    resp = app_client.patch(
        f"/api/v1/organisations/{organisation.id}", headers=admin, json={"name": "Renamed Org"}
    )
    assert resp.status_code == 200, resp.text

    rows = _audit_rows(db, AuditEntity.ORGANISATION, organisation.id)
    assert len(rows) == 1
    assert rows[0].action == AuditAction.UPDATE.value
    assert rows[0].changes == {"name": {"from": "Test Org", "to": "Renamed Org"}}


def test_job_creation_is_audited_without_copying_the_payload(
    app_client: TestClient, db: Session, as_user: UserFactory
) -> None:
    _, engineer = as_user(Role.ENGINEER)

    created = app_client.post(
        "/api/v1/jobs",
        headers=engineer,
        json={"kind": "health_check", "payload": {"secret_ish": "do-not-copy"}},
    )
    assert created.status_code == 202, created.text

    rows = _audit_rows(db, AuditEntity.JOB, created.json()["id"])
    assert len(rows) == 1
    assert rows[0].action == AuditAction.CREATE.value
    assert rows[0].changes == {"kind": "health_check", "project_id": None}
    assert "do-not-copy" not in str(rows[0].changes)


def test_a_rejected_mutation_writes_no_audit_row(
    app_client: TestClient, db: Session, as_user: UserFactory
) -> None:
    """Forbidden and conflicting actions leave the trail clean."""
    _, qe = as_user(Role.QUALITY_ENGINEER)
    before = db.execute(select(AuditLog)).scalars().all()

    denied = app_client.post(
        "/api/v1/users", headers=qe, json={"email": f"nope-{uuid.uuid4().hex}@example.com"}
    )
    assert denied.status_code == 403

    after = db.execute(select(AuditLog)).scalars().all()
    assert len(after) == len(before)


def test_a_failed_write_rolls_the_audit_row_back_with_it(
    app_client: TestClient, db: Session, as_user: UserFactory
) -> None:
    """The action and its audit row share one transaction (ADR-0108)."""
    _, admin = as_user(Role.ADMINISTRATOR)
    email = f"dup-{uuid.uuid4().hex}@example.com"
    first = app_client.post("/api/v1/users", headers=admin, json={"email": email})
    assert first.status_code == 201

    clash = app_client.post("/api/v1/users", headers=admin, json={"email": email})
    assert clash.status_code == 409

    matching = (
        db.execute(select(AuditLog).where(AuditLog.changes["email"].astext == email))
        .scalars()
        .all()
    )
    assert len(matching) == 1, "the conflicting attempt left no audit row"


def test_the_audit_endpoint_is_readable_by_a_lead_and_filterable(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, lead = as_user(Role.QE_LEAD)
    created = app_client.post(
        "/api/v1/projects", headers=lead, json={"name": f"Trail {uuid.uuid4().hex[:6]}"}
    )
    project_id = created.json()["id"]

    listed = app_client.get(
        f"/api/v1/audit-logs?entity_type=project&entity_id={project_id}", headers=lead
    )

    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 1
    entry = body["items"][0]
    assert entry["action"] == "CREATE"
    assert entry["entity_type"] == "project"
    assert entry["entity_id"] == project_id
    assert entry["actor_email"]


def test_engineers_cannot_read_the_audit_trail(
    app_client: TestClient, as_user: UserFactory
) -> None:
    _, engineer = as_user(Role.ENGINEER)

    resp = app_client.get("/api/v1/audit-logs", headers=engineer)

    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_the_audit_trail_is_tenant_scoped(
    app_client: TestClient, db: Session, as_user: UserFactory, other_organisation: Organisation
) -> None:
    foreign = AuditLog(
        organisation_id=other_organisation.id,
        action=AuditAction.CREATE.value,
        entity_type=AuditEntity.PROJECT.value,
        entity_id=uuid.uuid4(),
    )
    db.add(foreign)
    db.commit()
    db.refresh(foreign)
    _, lead = as_user(Role.QE_LEAD)

    listed = app_client.get("/api/v1/audit-logs", headers=lead).json()

    assert str(foreign.id) not in [item["id"] for item in listed["items"]]


def test_audit_routes_require_authentication(app_client: TestClient) -> None:
    assert app_client.get("/api/v1/audit-logs").status_code == 401
