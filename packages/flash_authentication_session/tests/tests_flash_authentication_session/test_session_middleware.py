import logging
import unittest.mock
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from flash_authentication.models import User
from flash_authentication.schemas import AnonymousUser, AuthenticationResult
from flash_authentication_session.backend import SESSION_COOKIE_NAME
from flash_authentication_session.middleware import SessionAuthenticationMiddleware
from flash_authentication_session.models import UserSession
from flash_db import db as db_module
from flash_db.models import Model
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def middleware_app(db_session: AsyncSession) -> FastAPI:  # noqa: ARG001
    """
    Creates a FastAPI app specifically for testing the SessionAuthenticationMiddleware.
    Depends on db_session to ensure the database is initialized.
    """
    app = FastAPI()

    # Get the session factory initialized by init_test_db (via db_session fixture)
    factory = db_module._require_session_factory()

    # Add the middleware
    app.add_middleware(SessionAuthenticationMiddleware, session_maker=factory)  # ty:ignore[invalid-argument-type]

    @app.get("/me")
    def me(request: Request) -> dict:
        user = request.state.user
        return {
            "username": getattr(user, "username", None),
            "user_id": getattr(user, "id", None),
        }

    return app


@pytest_asyncio.fixture
async def middleware_client(
    middleware_app: FastAPI,
) -> AsyncGenerator[AsyncClient, None]:
    """Client for the middleware test app."""
    transport = ASGITransport(app=middleware_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
class TestSessionMiddleware:
    async def test_request_without_cookie(self, middleware_client: AsyncClient) -> None:
        """Test that requests without a cookie result in AnonymousUser."""
        response: Response = await middleware_client.get("/me")

        assert response.status_code == 200
        data = response.json()
        assert not data["user_id"]
        assert not data["username"]

    async def test_request_with_valid_session(
        self, middleware_client: AsyncClient, test_user: User, db_session: AsyncSession
    ) -> None:
        """Test that a valid session cookie authenticates the user."""
        # 1. Create a session in DB
        session = UserSession(
            user_id=test_user.id,
            ip_address="127.0.0.1",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        # 2. Set cookie on client
        middleware_client.cookies.set(SESSION_COOKIE_NAME, session.session_key)

        # 3. Request
        response: Response = await middleware_client.get("/me")

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == test_user.username
        assert data["user_id"] == test_user.id

    async def test_request_with_invalid_token(
        self, middleware_client: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that an invalid token results in AnonymousUser
        and logs debug message."""
        # Explicitly enable debug logging for the middleware package to ensure capture
        logger = logging.getLogger("flash_authentication_session.middleware")
        logger.setLevel(logging.DEBUG)

        with caplog.at_level(
            logging.DEBUG, logger="flash_authentication_session.middleware"
        ):
            middleware_client.cookies.set(SESSION_COOKIE_NAME, "invalid_token_123")

            response: Response = await middleware_client.get("/me")

            assert response.status_code == 200
            data = response.json()
            assert data["username"] == AnonymousUser().username

            # Verify that the failure path was hit (Lines 47-51 coverage)
            assert "Authentication failed for token ending in" in caplog.text
            assert "_123" in caplog.text

    async def test_authentication_failure_logging_mocked(
        self, middleware_client: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        Test that the middleware logs a debug message when authentication fails
        with a message, ensuring lines 47-51 are covered strictly.
        """
        # Explicitly enable debug logging
        logger = logging.getLogger("flash_authentication_session.middleware")
        logger.setLevel(logging.DEBUG)

        # Define an async side effect to properly simulate await backend.authenticate()
        async def mock_authenticate(*args, **kwargs):  # noqa: ARG001
            return AuthenticationResult(
                success=False,
                user=AnonymousUser(),
                message="Forced Mock Failure",
                errors=[],
            )

        with (
            unittest.mock.patch(
                "flash_authentication_session.middleware.SessionAuthenticationBackend.authenticate"
            ) as mock_auth,
            caplog.at_level(
                logging.DEBUG, logger="flash_authentication_session.middleware"
            ),
        ):
            # Use side_effect with the async function
            mock_auth.side_effect = mock_authenticate

            middleware_client.cookies.set(SESSION_COOKIE_NAME, "mock_token_9999")

            response: Response = await middleware_client.get("/me")

            assert response.status_code == 200
            # Ensure the specific branch logic (logging) was executed
            assert (
                "Authentication failed for token ending in ...9999: Forced Mock Failure"
                in caplog.text
            )

    async def test_authentication_success_expunge_model(self) -> None:
        """
        Test that if authentication succeeds and user is a Model,
        db.expunge(user) is called.
        """
        # Mock dependencies
        mock_db = unittest.mock.AsyncMock(spec=AsyncSession)
        mock_factory = unittest.mock.MagicMock()
        mock_factory.return_value.__aenter__.return_value = mock_db
        mock_factory.return_value.__aexit__.return_value = None

        # Mock User as a Model instance
        mock_user = unittest.mock.MagicMock(spec=Model)

        # Mock Backend Result
        auth_result = AuthenticationResult(
            success=True,
            user=mock_user,
            message="Success",
            extra={"session": "session_obj"},
        )

        # Mock App
        async def mock_app(scope: Any, receive: Any, send: Any) -> None:
            pass

        # Instantiate Middleware directly
        middleware = SessionAuthenticationMiddleware(
            mock_app, session_maker=mock_factory
        )

        # Patch authenticate
        with unittest.mock.patch.object(
            middleware.backend, "authenticate", return_value=auth_result
        ):
            # Construct scope with cookie
            scope = {
                "type": "http",
                "headers": [(b"cookie", f"{SESSION_COOKIE_NAME}=token".encode())],
            }

            async def receive() -> Any:
                pass

            async def send(msg: Any) -> None:
                pass

            await middleware(scope, receive, send)

            # Assertions
            mock_db.expunge.assert_called_once_with(mock_user)

    async def test_request_with_expired_session(
        self, middleware_client: AsyncClient, test_user: User, db_session: AsyncSession
    ) -> None:
        """Test that an expired session results in AnonymousUser."""
        # 1. Create expired session
        session = UserSession(
            user_id=test_user.id,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(session)
        await db_session.commit()

        # 2. Set cookie
        middleware_client.cookies.set(SESSION_COOKIE_NAME, session.session_key)

        # 3. Request
        response: Response = await middleware_client.get("/me")

        assert response.status_code == 200
        data = response.json()

        assert data["username"] == AnonymousUser().username

    async def test_db_error_handling(
        self, middleware_client: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that DB errors during auth are caught, logged, and result in
        AnonymousUser."""
        with (
            unittest.mock.patch(
                "flash_authentication_session.middleware.SessionAuthenticationBackend.authenticate"
            ) as mock_auth,
            caplog.at_level(
                logging.ERROR, logger="flash_authentication_session.middleware"
            ),
        ):
            mock_auth.side_effect = Exception("DB Connection Failed")

            # Set a cookie so it attempts auth
            middleware_client.cookies.set(SESSION_COOKIE_NAME, "any_token")

            response: Response = await middleware_client.get("/me")

            # Should still return 200 OK (Anonymous), not 500 Internal Error
            assert response.status_code == 200
            assert response.json()["username"] == AnonymousUser().username

            # Verify the exception was actually caught and logged
            assert (
                "Authentication middleware encountered an unexpected error"
                in caplog.text
            )

    async def test_lifespan_scope_ignored(self, db_session: AsyncSession) -> None:  # noqa: ARG002
        """
        Test that non-HTTP/WebSocket scopes (like lifespan) are passed through
        without authentication logic.
        """
        # Mock the app (next middleware/app in chain)
        app_called = False

        async def mock_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ARG001
            nonlocal app_called
            app_called = True

        # Get session factory (Requires db_session fixture to ensure initialization)
        factory = db_module._require_session_factory()

        # Instantiate middleware directly to bypass framework behaviors
        middleware = SessionAuthenticationMiddleware(mock_app, session_maker=factory)

        # Create lifespan scope
        scope = {"type": "lifespan"}

        async def receive() -> Any:
            pass

        async def send(msg: Any) -> None:
            pass

        # Call middleware directly
        await middleware(scope, receive, send)

        # Assert app was called (passed through)
        assert app_called

        # Assert state was NOT touched (middleware sets request.state.user if it runs)
        # request.state relies on scope["state"]
        assert "state" not in scope
