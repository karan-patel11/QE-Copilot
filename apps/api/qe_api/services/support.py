"""Small helpers shared by the service layer."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from qe_common.errors import ConflictError

# Pagination bounds applied to every list endpoint.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


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


__all__ = ["DEFAULT_LIMIT", "MAX_LIMIT", "commit_or_conflict"]
