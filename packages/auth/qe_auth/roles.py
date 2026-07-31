"""Platform roles and the role → permission matrix (ADR-0104, ADR-0105).

Route guards depend on :class:`Permission` values, never on role names, so
:data:`ROLE_PERMISSIONS` is the single place authorisation policy changes.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class Role(StrEnum):
    """The five design roles (mirrors the seeded ``roles`` table)."""

    ENGINEER = "engineer"
    QUALITY_ENGINEER = "quality_engineer"
    QE_LEAD = "qe_lead"
    PLATFORM_ENGINEER = "platform_engineer"
    ADMINISTRATOR = "administrator"


ROLE_DESCRIPTIONS: dict[Role, str] = {
    Role.ENGINEER: "Writes product code; consumes generated tests and triage output.",
    Role.QUALITY_ENGINEER: "Owns test assets for a project; curates repositories and jobs.",
    Role.QE_LEAD: "Leads quality for an organisation; manages projects and reviews audits.",
    Role.PLATFORM_ENGINEER: "Operates the platform; manages projects, repositories, and health.",
    Role.ADMINISTRATOR: "Full administrative control, including users and role assignment.",
}


class Permission(StrEnum):
    """Fine-grained capabilities checked by route guards and services."""

    ORGANISATION_READ = "organisation:read"
    ORGANISATION_WRITE = "organisation:write"
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    ROLE_ASSIGN = "role:assign"
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"
    REPOSITORY_READ = "repository:read"
    REPOSITORY_WRITE = "repository:write"
    JOB_READ = "job:read"
    JOB_CREATE = "job:create"
    AUDIT_READ = "audit:read"
    SYSTEM_READ = "system:read"
    TEST_GENERATION_READ = "test_generation:read"
    TEST_GENERATION_CREATE = "test_generation:create"
    TEST_CASE_REVIEW = "test_case:review"


_ENGINEER_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.ORGANISATION_READ,
        Permission.PROJECT_READ,
        Permission.REPOSITORY_READ,
        Permission.JOB_READ,
        Permission.JOB_CREATE,
        Permission.SYSTEM_READ,
        # Reading generated tests is available to every role, including the
        # operations role that may not author or approve them.
        Permission.TEST_GENERATION_READ,
    }
)

#: Creating a generation and ruling on its output — a quality judgement, not an
#: operational one. Composed onto three roles **explicitly** rather than added to
#: the Engineer base set, because the base sets form a chain
#: (ENGINEER ⊂ QUALITY_ENGINEER ⊂ PLATFORM_ENGINEER) and anything granted to
#: Engineer would reach Platform Engineer transitively. §6.4 makes Platform
#: Engineer an operations role; approving a test is not an operational act
#: (ADR-0212). A future reader tidying this back into the chain would silently
#: grant approval rights to Platform Engineer — which is why it is spelled out.
_TEST_GENERATION_AUTHOR: frozenset[Permission] = frozenset(
    {
        Permission.TEST_GENERATION_CREATE,
        Permission.TEST_CASE_REVIEW,
    }
)

_QUALITY_ENGINEER_PERMISSIONS: frozenset[Permission] = _ENGINEER_PERMISSIONS | {
    Permission.REPOSITORY_WRITE,
}

_QE_LEAD_PERMISSIONS: frozenset[Permission] = _QUALITY_ENGINEER_PERMISSIONS | {
    Permission.PROJECT_WRITE,
    Permission.USER_READ,
    Permission.AUDIT_READ,
}

_PLATFORM_ENGINEER_PERMISSIONS: frozenset[Permission] = _QUALITY_ENGINEER_PERMISSIONS | {
    Permission.PROJECT_WRITE,
    Permission.AUDIT_READ,
}

# Administrators hold every permission by construction, so a newly added
# permission is never silently withheld from them.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ENGINEER: _ENGINEER_PERMISSIONS | _TEST_GENERATION_AUTHOR,
    Role.QUALITY_ENGINEER: _QUALITY_ENGINEER_PERMISSIONS | _TEST_GENERATION_AUTHOR,
    Role.QE_LEAD: _QE_LEAD_PERMISSIONS | _TEST_GENERATION_AUTHOR,
    # Read-only on test generation, deliberately — see _TEST_GENERATION_AUTHOR.
    Role.PLATFORM_ENGINEER: _PLATFORM_ENGINEER_PERMISSIONS,
    Role.ADMINISTRATOR: frozenset(Permission),
}


def permissions_for(roles: Iterable[Role]) -> frozenset[Permission]:
    """Return the union of permissions granted by ``roles``."""
    granted: set[Permission] = set()
    for role in roles:
        granted |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(granted)


def parse_role(name: str) -> Role | None:
    """Return the :class:`Role` for ``name``, or ``None`` if it is not a known role.

    Role rows are seeded by migration, but the database is not the source of
    truth for policy: an unrecognised row grants nothing rather than crashing
    request handling.
    """
    try:
        return Role(name)
    except ValueError:
        return None


__all__ = [
    "ROLE_DESCRIPTIONS",
    "ROLE_PERMISSIONS",
    "Permission",
    "Role",
    "parse_role",
    "permissions_for",
]
