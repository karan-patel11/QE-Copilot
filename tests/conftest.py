"""Shared fixtures.

Integration tests run against the live Postgres/Redis from the Compose stack
(the same services CI provides). Isolation comes from creating a throwaway
organisation per test and deleting it afterwards: every Phase 1 table is rooted
at ``organisations`` through ``ON DELETE CASCADE``, so one delete removes every
row a test produced. Committing for real — rather than rolling back a wrapping
transaction — is required because the worker observes the database from a
separate process.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from qe_api.main import create_app
from qe_auth import Role
from qe_database.models import Organisation, User
from qe_database.session import get_engine
from tests.helpers import UserFactory, auth_header, make_organisation, make_user


@pytest.fixture(scope="session")
def app_client() -> Iterator[TestClient]:
    """A TestClient over the real application (no dependency overrides)."""
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        yield client


@pytest.fixture()
def db() -> Iterator[Session]:
    """A short-lived synchronous session for arranging/asserting test data."""
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session


def _tenant(db: Session, prefix: str) -> Iterator[Organisation]:
    org = make_organisation(db, prefix)
    try:
        yield org
    finally:
        db.execute(delete(Organisation).where(Organisation.id == org.id))
        db.commit()


@pytest.fixture()
def organisation(db: Session) -> Iterator[Organisation]:
    """A throwaway tenant; every row created beneath it is cascade-deleted."""
    yield from _tenant(db, "test-org")


@pytest.fixture()
def other_organisation(db: Session) -> Iterator[Organisation]:
    """A second tenant, used to prove cross-tenant isolation."""
    yield from _tenant(db, "other-org")


@pytest.fixture()
def as_user(db: Session, organisation: Organisation) -> UserFactory:
    """Factory creating a user with the given roles plus its auth header."""

    def _factory(*roles: Role, org: Organisation | None = None) -> tuple[User, dict[str, str]]:
        user = make_user(db, org or organisation, *roles)
        return user, auth_header(user, roles)

    return _factory
