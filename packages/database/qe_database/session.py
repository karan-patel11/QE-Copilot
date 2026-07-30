"""Engine and session factories (sync for migrations, async for the API).

ADR-0008: psycopg v3 with SQLAlchemy 2.0. Engines are created lazily and cached
so importing this module has no side effects (nothing connects at import time).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from qe_common.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide sync engine (used by Alembic and the worker)."""
    return create_engine(get_settings().database_url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_async_engine() -> AsyncEngine:
    """Return the process-wide async engine (used by the API)."""
    return create_async_engine(
        get_settings().async_database_url, pool_pre_ping=True, future=True
    )


@lru_cache(maxsize=1)
def _sync_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, class_=Session)


@lru_cache(maxsize=1)
def _async_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_async_engine(), expire_on_commit=False, class_=AsyncSession
    )


def get_session() -> Iterator[Session]:
    """Yield a sync session (worker / scripts)."""
    session = _sync_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Yield an async session (FastAPI dependency)."""
    async with _async_session_factory()() as session:
        yield session
