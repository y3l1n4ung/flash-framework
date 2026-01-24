import asyncio

import pytest
import pytest_asyncio
from flash_db import db as db_module
from flash_db.models import Model

DATABASE_URL = "sqlite+aiosqlite:///:memory:"  # in-memory DB for tests


@pytest.fixture(scope="session")
def event_loop():
    """Provide an asyncio event loop for pytest-asyncio."""
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def init_test_db():
    """Initialize the test database before any tests run."""
    # Initialize DB engine and session factory
    db_module.init_db(DATABASE_URL, echo=False)

    # Create all tables
    async_engine = db_module._engine  # access engine from db.py
    assert async_engine is not None

    async with async_engine.begin() as conn:
        await conn.run_sync(Model.metadata.create_all)

    yield

    # Dispose engine after all tests
    await db_module.close_db()


@pytest_asyncio.fixture()
async def db_session(init_test_db):
    """Provide a database session for tests."""

    async for session in db_module.get_db():
        yield session
