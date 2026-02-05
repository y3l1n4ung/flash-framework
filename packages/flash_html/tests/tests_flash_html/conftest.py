import asyncio

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from flash_authentication import AnonymousUser, User
from flash_db import db as db_module
from flash_db.models import Model
from flash_html.template_manager import TemplateManager
from sqlalchemy.ext.asyncio import AsyncSession

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
async def db_session(init_test_db):  # noqa: ARG001
    """Provide a database session for tests."""
    async for session in db_module.get_db():
        yield session


@pytest.fixture
def manager(tmp_path):
    """Creates a TemplateManager with explicit template files."""
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)

    # Explicit templates used for verification
    (tpl_dir / "product_detail.html").write_text("Product: {{ htmltestproduct.name }}")
    (tpl_dir / "blog_detail.html").write_text("Post: {{ htmltestblog.title }}")
    (tpl_dir / "article_detail.html").write_text(
        "HTMLTestArticle: {{ htmltestarticle.title }} "
        "by {{ htmltestarticle.author_id }}"
    )
    (tpl_dir / "custom.html").write_text("Custom: {{ object.name }}")
    (tpl_dir / "extra.html").write_text("Extra: {{ name }}")
    (tpl_dir / "item_test.html").write_text("Item: {{ item.name }}")

    return TemplateManager(project_root=tmp_path)


@pytest.fixture
def app(manager):
    """Creates a FastAPI app with the manager attached to state."""
    from fastapi import Request
    from flash_authentication import AnonymousUser

    app = FastAPI()
    app.state.template_manager = manager
    app.state.test_user = AnonymousUser()  # Default to anonymous user

    # Add middleware to set user from app.state to request.state
    @app.middleware("http")
    async def set_user_middleware(request: Request, call_next):
        # Copy user from app.state to request.state for each request
        request.state.user = getattr(app.state, "test_user", AnonymousUser())
        return await call_next(request)

    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# User fixtures for permission testing
@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession):
    """Creates a basic active user for testing."""
    user = User(
        username="testuser",
        email="test@example.com",
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )
    user.set_password("password123")

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def admin_user(db_session: AsyncSession):
    """Creates an admin user (staff and superuser)."""
    user = User(
        username="admin",
        email="admin@example.com",
        is_active=True,
        is_staff=True,
        is_superuser=True,
    )
    user.set_password("admin123")

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def staff_user(db_session: AsyncSession):
    """Creates a staff user (not superuser)."""
    user = User(
        username="staff",
        email="staff@example.com",
        is_active=True,
        is_staff=True,
        is_superuser=False,
    )
    user.set_password("staff123")

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def blog_user(db_session: AsyncSession):
    """Creates a regular user for blog/article ownership testing."""
    user = User(
        username="blogger",
        email="blog@example.com",
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )
    user.set_password("blog123")

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def anon_user():
    """Returns an anonymous user."""
    return AnonymousUser()
