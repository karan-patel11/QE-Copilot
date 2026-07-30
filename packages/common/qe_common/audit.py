"""Audit vocabulary.

Kept next to the other shared enums (and free of ORM imports) so the API, the
worker, and any future consumer name actions and entities identically.
"""

from __future__ import annotations

from enum import StrEnum


class AuditAction(StrEnum):
    """The mutating actions the platform records."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class AuditEntity(StrEnum):
    """Entity types an audit row can refer to."""

    ORGANISATION = "organisation"
    USER = "user"
    USER_ROLES = "user_roles"
    PROJECT = "project"
    REPOSITORY = "repository"
    JOB = "job"


__all__ = ["AuditAction", "AuditEntity"]
