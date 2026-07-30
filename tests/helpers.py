"""Helpers shared by fixtures and tests.

Kept out of ``conftest.py`` so tests can import these symbols by module path
without colliding with the copy pytest auto-loads as a top-level ``conftest``.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from qe_auth import Role, issue_token
from qe_database.models import Organisation, User
from qe_database.models import Role as RoleRow


def make_organisation(db: Session, prefix: str) -> Organisation:
    """Create a throwaway tenant with a collision-proof slug."""
    org = Organisation(name=prefix.replace("-", " ").title(), slug=f"{prefix}-{uuid.uuid4().hex}")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def make_user(db: Session, organisation: Organisation, *roles: Role) -> User:
    """Create an active user in ``organisation`` holding ``roles``."""
    user = User(
        organisation_id=organisation.id,
        email=f"user-{uuid.uuid4().hex}@example.com",
        full_name="Test User",
        is_active=True,
    )
    for role in roles:
        row = db.execute(select(RoleRow).where(RoleRow.name == role.value)).scalar_one()
        user.roles.append(row)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def auth_header(user: User, roles: tuple[Role, ...] = ()) -> dict[str, str]:
    """Build an ``Authorization`` header carrying a freshly issued token."""
    token, _ = issue_token(
        user_id=user.id,
        organisation_id=user.organisation_id,
        email=user.email,
        roles=frozenset(roles),
    )
    return {"Authorization": f"Bearer {token}"}


class UserFactory(Protocol):
    """``as_user(Role.ENGINEER)`` -> ``(user, authorization headers)``."""

    def __call__(
        self, *roles: Role, org: Organisation | None = None
    ) -> tuple[User, dict[str, str]]: ...


__all__ = ["UserFactory", "auth_header", "make_organisation", "make_user"]
