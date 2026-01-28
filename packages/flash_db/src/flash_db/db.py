from collections.abc import AsyncGenerator
from typing import Any, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """
    Enable SQLite foreign key enforcement for every DBAPI connection.
    """

    @event.listens_for(engine.sync_engine.pool, "connect")  # pragma: no cover
    def _set_sqlite_pragma(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db(
    database_url: str,
    *,
    echo: bool = False,
    **engine_kwargs: Any,
) -> None:
    """
    Initialize async SQLAlchemy engine and session factory.

    Supports:
    - SQLite (aiosqlite)
    - PostgreSQL (asyncpg)
    """
    global _engine, _session_factory

    # Normalize PostgreSQL async driver
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    is_sqlite = database_url.startswith("sqlite")

    options: dict[str, Any] = {
        "echo": echo,
        **engine_kwargs,
    }

    if is_sqlite:
        # SQLite does not support pooling options
        options.pop("pool_size", None)
        options.pop("max_overflow", None)
        options.pop("pool_pre_ping", None)
        options.setdefault("connect_args", {"check_same_thread": False})
    else:
        options.setdefault("pool_pre_ping", True)

    _engine = create_async_engine(database_url, **options)

    if is_sqlite:
        _enable_sqlite_foreign_keys(_engine)

    _session_factory = async_sessionmaker(
        bind=_engine,
        expire_on_commit=False,
        autoflush=False,
    )


async def close_db() -> None:
    """Dispose database engine."""
    if _engine is not None:
        await _engine.dispose()


def _require_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        msg = "Database not initialized. Call init_db() first."
        raise RuntimeError(msg)
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency-style async session generator.
    """
    factory = _require_session_factory()
    async with factory() as session:
        yield session
