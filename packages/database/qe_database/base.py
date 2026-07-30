"""Declarative base and shared column mixins."""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class UUIDPrimaryKeyMixin:
    """ADR-0011: non-guessable UUID primary keys via ``gen_random_uuid()``."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )


class TimestampMixin:
    """Created/updated audit timestamps managed by the database."""

    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
