import asyncio

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.testclient import TestClient
from flash_authentication import User
from flash_authentication_session.backend import (
    SESSION_COOKIE_NAME,
    SessionAuthenticationBackend,
)
from flash_db import db as db_module
from flash_db.models import Model
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

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


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession):
    """
    Creates a basic active user for testing.
    We assume the User model has username, email, and is_active fields.
    """
    user = User(
        username="testuser",
        email="test@example.com",
        is_active=True,
    )
    user.set_password("password123")

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def inactive_test_user(db_session: AsyncSession):
    """Creates an inactive user."""
    user = User(
        username="inactive",
        email="inactive@example.com",
        is_active=False,
    )
    user.set_password("password123")

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def backend():
    return SessionAuthenticationBackend()


@pytest.fixture
def test_app(db_session, backend):
    """
    Creates a temporary FastAPI app with SessionMiddleware for testing the backend.
    We inject the test `db_session` into the routes to ensure they share state.
    """
    app = FastAPI()

    # SessionMiddleware is required for request.session to work
    app.add_middleware(
        SessionMiddleware,  # ty:ignore[invalid-argument-type]
        secret_key="secret-key-for-testing",
        https_only=False,  # Allow http for tests
    )

    # Dependency to yield the existing test session
    async def get_test_db():
        yield db_session

    # -- Test Routes --

    @app.post("/login")
    async def login_route(
        request: Request, payload: dict, db: AsyncSession = Depends(get_test_db)
    ):
        result = await backend.login(
            request,
            db,
            username=payload.get("username"),
            email=payload.get("email"),
            password=payload.get("password"),
        )
        if not result.success:
            # We return 401 to easily check failure in client
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=result.message
            )
        return {"message": result.message, "user": result.user.id}

    @app.post("/logout")
    async def logout_route(request: Request, db: AsyncSession = Depends(get_test_db)):
        success = await backend.logout(request, db)
        return {"success": success}

    @app.get("/verify")
    async def verify_route(request: Request, db: AsyncSession = Depends(get_test_db)):
        """
        Simulates a protected route.
        It manually grabs the token from the session and calls authenticate.
        """
        token = request.session.get(SESSION_COOKIE_NAME)
        if not token:
            raise HTTPException(status_code=401, detail="No session token")

        result = await backend.authenticate(db, token)
        if not result.success:
            raise HTTPException(status_code=401, detail=result.message)

        return {"user_id": result.user.id, "session_key": token}

    return app


@pytest.fixture
def client(test_app):
    """Returns a TestClient instance wrapped around the session test app."""
    with TestClient(test_app) as c:
        yield c
