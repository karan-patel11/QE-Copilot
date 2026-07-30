"""Small helpers shared by the service layer."""

from __future__ import annotations

import re
from typing import TypeVar

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from qe_common.errors import ConflictError, ValidationAppError

_Instance = TypeVar("_Instance")

# Pagination bounds applied to every list endpoint.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Derive a URL-safe slug from ``value``.

    Raises :class:`ValidationAppError` when nothing usable survives, rather than
    silently producing an empty slug that would collide with the next one.
    """
    slug = _SLUG_STRIP.sub("-", value.strip().lower()).strip("-")
    if not slug:
        raise ValidationAppError("A slug could not be derived; provide one explicitly.")
    return slug[:255]


async def commit_or_conflict(session: AsyncSession, message: str) -> None:
    """Commit, translating a unique/foreign-key violation into a 409.

    Uniqueness is enforced by the database rather than by a read-then-write
    check, so concurrent requests cannot both pass a pre-flight test and then
    both insert.
    """
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(message) from exc


async def commit_and_refresh(session: AsyncSession, instance: _Instance, message: str) -> _Instance:
    """Commit, then reload ``instance``.

    ``updated_at`` is computed by the database (``onupdate=now()``), so after an
    UPDATE the attribute is expired. Reading it would trigger lazy IO from a
    context that cannot await, which surfaces as ``MissingGreenlet`` — the
    refresh performs that IO explicitly instead.
    """
    await commit_or_conflict(session, message)
    await session.refresh(instance)
    return instance


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "commit_and_refresh",
    "commit_or_conflict",
    "slugify",
]
