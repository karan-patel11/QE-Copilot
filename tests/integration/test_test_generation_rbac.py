"""N6 RBAC: a real 403 for every denied role/route pair, not one smoke test.

§26.2 L2100-2103 requires the check at the API-route level as well as the
service level. These assert the route-level guard: the request is rejected before
the handler body runs, which is why a nonexistent resource id still yields 403
rather than 404 — the guard fires first.

Parametrised over role and route so a permission accidentally widened shows up as
one named failure, e.g. ``[platform_engineer-approve]``, rather than as a single
opaque red smoke test.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from qe_auth import Permission, Role
from qe_auth.roles import ROLE_PERMISSIONS
from qe_database.models import Organisation, Project
from tests.helpers import UserFactory

pytestmark = pytest.mark.integration

BASE = "/api/v1/test-generation"
CASES = "/api/v1/generated-tests"

#: Routes that require authoring or review rights, with the permission each one
#: guards. ``id`` values are arbitrary: the guard runs before any lookup.
_WRITE_ROUTES: list[tuple[str, str, str, Permission]] = [
    ("create", "POST", f"{BASE}/requests", Permission.TEST_GENERATION_CREATE),
    ("approve", "POST", f"{CASES}/{{id}}/approve", Permission.TEST_CASE_REVIEW),
    ("reject", "POST", f"{CASES}/{{id}}/reject", Permission.TEST_CASE_REVIEW),
    ("regenerate", "POST", f"{CASES}/{{id}}/regenerate", Permission.TEST_GENERATION_CREATE),
    ("validate", "POST", f"{CASES}/{{id}}/validate", Permission.TEST_CASE_REVIEW),
]

#: The one role that may read generated tests but must never author or approve
#: them: §6.4 makes Platform Engineer an operations role, and approving a test is
#: a quality judgement (ADR-0212).
_DENIED_ROLES: list[Role] = [Role.PLATFORM_ENGINEER]

_ALLOWED_AUTHOR_ROLES: list[Role] = [Role.ENGINEER, Role.QUALITY_ENGINEER, Role.QE_LEAD]


@pytest.fixture()
def project(db: Session, organisation: Organisation) -> Project:
    row = Project(
        organisation_id=organisation.id,
        name="RBAC",
        slug=f"rbac-{uuid.uuid4().hex[:8]}",
        description="",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _body(route_id: str, project: Project) -> dict[str, Any] | None:
    if route_id != "create":
        return None
    return {
        "project_id": str(project.id),
        "title": "Denied",
        "source_reference": "A subscriber resumes playback.",
        "configuration": {},
    }


@pytest.mark.parametrize("role", _DENIED_ROLES, ids=lambda r: r.value)
@pytest.mark.parametrize("route", _WRITE_ROUTES, ids=lambda r: r[0])
def test_denied_role_gets_403_on_each_write_route(
    app_client: TestClient,
    as_user: UserFactory,
    project: Project,
    role: Role,
    route: tuple[str, str, str, Permission],
) -> None:
    """One real 403 per role/route pair, asserted on the envelope."""
    route_id, method, path, permission = route
    _, headers = as_user(role)

    response = app_client.request(
        method,
        path.format(id=uuid.uuid4()),
        json=_body(route_id, project),
        headers=headers,
    )

    assert response.status_code == 403, f"{role.value} should not reach {route_id}: {response.text}"
    envelope = response.json()
    assert envelope["error"]["code"] == "FORBIDDEN"
    assert permission.value in envelope["error"]["message"]


@pytest.mark.parametrize("role", _ALLOWED_AUTHOR_ROLES, ids=lambda r: r.value)
def test_author_roles_may_create(
    app_client: TestClient, as_user: UserFactory, project: Project, role: Role
) -> None:
    """The positive half: the same routes must actually work for allowed roles.

    Without this, granting nobody anything would pass the 403 tests above.
    """
    _, headers = as_user(role)
    response = app_client.post(f"{BASE}/requests", json=_body("create", project), headers=headers)
    assert response.status_code == 202, response.text


def test_a_denied_role_can_still_read(
    app_client: TestClient, as_user: UserFactory, project: Project
) -> None:
    """Platform Engineer holds READ — the denial is scoped, not blanket."""
    _, headers = as_user(Role.PLATFORM_ENGINEER)
    response = app_client.get(f"{BASE}/requests/{uuid.uuid4()}", headers=headers)
    # 404 rather than 403 proves the read guard passed and the lookup ran.
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_unauthenticated_requests_are_rejected(app_client: TestClient) -> None:
    response = app_client.get(f"{BASE}/requests/{uuid.uuid4()}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_another_tenants_request_is_404_not_403(
    app_client: TestClient,
    db: Session,
    as_user: UserFactory,
    other_organisation: Organisation,
    project: Project,
) -> None:
    """Cross-tenant reads disclose nothing, including existence (ADR-0106)."""
    from qe_common.jobs import JobState
    from qe_common.test_generation import SourceType, TestFramework
    from qe_database.models import TestGenerationRequest

    other_project = Project(
        organisation_id=other_organisation.id,
        name="Other",
        slug=f"other-{uuid.uuid4().hex[:8]}",
        description="",
    )
    db.add(other_project)
    db.flush()
    foreign = TestGenerationRequest(
        organisation_id=other_organisation.id,
        project_id=other_project.id,
        title="Not yours",
        source_type=SourceType.REQUIREMENT_TEXT.value,
        source_reference="secret requirement",
        framework=TestFramework.PYTEST.value,
        status=JobState.PENDING.value,
        configuration={},
    )
    db.add(foreign)
    db.commit()

    _, headers = as_user(Role.QUALITY_ENGINEER)
    response = app_client.get(f"{BASE}/requests/{foreign.id}", headers=headers)
    assert response.status_code == 404
    assert "secret requirement" not in response.text


def test_the_role_matrix_matches_the_adr() -> None:
    """Guards enforce the matrix; this asserts the matrix itself (ADR-0212).

    Pinned because the base permission sets form a chain
    (ENGINEER ⊂ QUALITY_ENGINEER ⊂ PLATFORM_ENGINEER): anyone "tidying" the
    authoring permissions into the Engineer base set would silently grant
    approval rights to Platform Engineer, and every 403 test above would still
    pass for the roles it covers while this one fails.
    """
    author = {Permission.TEST_GENERATION_CREATE, Permission.TEST_CASE_REVIEW}
    for role in _ALLOWED_AUTHOR_ROLES:
        assert author <= ROLE_PERMISSIONS[role], role
    assert not (author & ROLE_PERMISSIONS[Role.PLATFORM_ENGINEER])
    assert Permission.TEST_GENERATION_READ in ROLE_PERMISSIONS[Role.PLATFORM_ENGINEER]
    assert author <= ROLE_PERMISSIONS[Role.ADMINISTRATOR]


def test_the_read_routes_require_a_role_not_merely_authentication(
    app_client: TestClient, as_user: UserFactory
) -> None:
    """Both GET routes are guarded by ``TEST_GENERATION_READ``.

    Every one of the five platform roles holds it, so in practice any role can
    read — but an authenticated user holding *no* role is refused. Asserted
    because "authenticated" and "authorised" are different guarantees and the
    distinction was previously only implicit in the dependency wiring.
    """
    _, headers = as_user()  # a real, active user with zero roles

    for path in (
        f"{BASE}/requests/{uuid.uuid4()}",
        f"{BASE}/requests/{uuid.uuid4()}/tests",
    ):
        response = app_client.get(path, headers=headers)
        assert response.status_code == 403, f"{path} must require a role: {response.text}"
        assert response.json()["error"]["code"] == "FORBIDDEN"
        assert Permission.TEST_GENERATION_READ.value in response.json()["error"]["message"]


@pytest.mark.parametrize(
    "role",
    [
        Role.ENGINEER,
        Role.QUALITY_ENGINEER,
        Role.QE_LEAD,
        Role.PLATFORM_ENGINEER,
        Role.ADMINISTRATOR,
    ],
    ids=lambda r: r.value,
)
def test_every_platform_role_can_read(
    app_client: TestClient, as_user: UserFactory, role: Role
) -> None:
    """The positive half: 404 (not 403) proves the read guard passed."""
    _, headers = as_user(role)
    response = app_client.get(f"{BASE}/requests/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404, response.text
