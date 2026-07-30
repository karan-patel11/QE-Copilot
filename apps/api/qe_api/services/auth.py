"""Identity-provider services.

Phase 1 ships the dev-mode identity provider (ADR-0101). It is mounted only when
``AUTH_DEV_MODE`` is true, and :class:`qe_common.config.Settings` refuses to
start a production process with it enabled.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from qe_auth import Role
from qe_common.config import Settings, get_settings
from qe_common.errors import NotFoundError, UnauthorizedError
from qe_database.models import Organisation, User
from qe_database.models import Role as RoleRow
from qe_observability import get_logger

logger = get_logger("qe_api.services.auth")


async def _get_or_create_default_organisation(
    session: AsyncSession, settings: Settings
) -> Organisation:
    """Return the dev organisation, creating it on first use."""
    slug = settings.auth_dev_organisation_slug
    stmt = select(Organisation).where(Organisation.slug == slug)
    org = (await session.execute(stmt)).scalar_one_or_none()
    if org is not None:
        return org

    org = Organisation(name=slug.replace("-", " ").title(), slug=slug)
    session.add(org)
    try:
        await session.flush()
    except IntegrityError:
        # Another request created it between the SELECT and the INSERT.
        await session.rollback()
        return (await session.execute(stmt)).scalar_one()
    return org


async def _role_row(session: AsyncSession, role: Role) -> RoleRow:
    row = (
        await session.execute(select(RoleRow).where(RoleRow.name == role.value))
    ).scalar_one_or_none()
    if row is None:  # pragma: no cover - migration 0002 seeds every role
        raise RuntimeError(f"role {role.value!r} is not seeded; run `alembic upgrade head`")
    return row


async def dev_login(session: AsyncSession, email: str, *, settings: Settings | None = None) -> User:
    """Resolve ``email`` to a user, provisioning it on first sign-in (ADR-0103).

    Roles are assigned only at creation time: an existing user keeps whatever
    ``user_roles`` says, so the dev provider can never escalate a real account.
    """
    resolved = settings or get_settings()
    if not resolved.auth_dev_mode:  # pragma: no cover - route is not mounted
        raise UnauthorizedError("The dev identity provider is disabled.")

    normalised = email.strip().lower()
    stmt = select(User).where(User.email == normalised).options(selectinload(User.roles))
    user = (await session.execute(stmt)).scalar_one_or_none()

    if user is not None:
        if not user.is_active:
            raise UnauthorizedError("This account is deactivated.")
        return user

    organisation = await _get_or_create_default_organisation(session, resolved)
    initial_role = (
        Role.ADMINISTRATOR
        if normalised == resolved.auth_dev_admin_email.strip().lower()
        else Role.ENGINEER
    )
    user = User(
        organisation_id=organisation.id,
        email=normalised,
        full_name=normalised.split("@")[0].replace(".", " ").title(),
        is_active=True,
    )
    user.roles.append(await _role_row(session, initial_role))
    session.add(user)
    await session.commit()

    refreshed = (await session.execute(stmt)).scalar_one()
    logger.info(
        "dev identity provider provisioned a user",
        extra={"event_type": "auth.dev_provision"},
    )
    return refreshed


async def load_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    """Load a user with its roles eagerly attached."""
    stmt = select(User).where(User.id == user_id).options(selectinload(User.roles))
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found.")
    return user


__all__ = ["dev_login", "load_user"]
