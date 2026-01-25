import asyncio

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from flash_db import db as db_module
from flash_db.models import Model
from flash_html.template_manager import TemplateManager

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


@pytest.fixture
def manager(tmp_path):
    """Creates a TemplateManager with explicit template files."""
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)

    # Explicit templates used for verification
    (tpl_dir / "product_detail.html").write_text("Product: {{ product.name }}")
    (tpl_dir / "blog_detail.html").write_text("Post: {{ blog.title }}")
    (tpl_dir / "custom.html").write_text("Custom: {{ object.name }}")
    (tpl_dir / "extra.html").write_text("Extra: {{ name }}")
    (tpl_dir / "item_test.html").write_text("Item: {{ item.name }}")

    return TemplateManager(project_root=tmp_path)


@pytest.fixture
def app(manager):
    """Creates a FastAPI app with the manager attached to state."""
    app = FastAPI()
    app.state.template_manager = manager
    return app


@pytest.fixture
def client(app):
    return TestClient(app)
