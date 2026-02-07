import logging
import unittest.mock
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from flash_authentication.models import User
from flash_authentication.schemas import AnonymousUser, AuthenticationResult
from flash_authentication_session.backend import SESSION_COOKIE_NAME
from flash_authentication_session.middleware import SessionAuthenticationMiddleware
from flash_authentication_session.models import UserSession
from flash_db import db as db_module
from flash_db.models import Model
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def middleware_app(db_session: AsyncSession) -> FastAPI:  # noqa: ARG001
    """FastAPI app integrated with Session and Authentication middlewares."""
    app = FastAPI()
    factory = db_module._require_session_factory()

    app.add_middleware(
        SessionAuthenticationMiddleware,  # ty:ignore[invalid-argument-type]
        session_maker=factory,
    )

    app.add_middleware(
        SessionMiddleware,  # ty:ignore[invalid-argument-type]
        secret_key="test-secret",
        session_cookie=SESSION_COOKIE_NAME,
        max_age=3600,
    )

    @app.get("/me")
    def me(request: Request):
        user = request.state.user
        return {
            "username": getattr(user, "username", None),
            "user_id": getattr(user, "id", None),
        }

    @app.post("/force_session/{key}")
    def force_session(request: Request, key: str):
        request.session[SESSION_COOKIE_NAME] = key
        return {"status": "set"}

    return app


@pytest.fixture
def client(middleware_app: FastAPI) -> TestClient:
    """TestClient for E2E tests."""
    return TestClient(middleware_app)


class TestSessionMiddlewareE2E:
    """End-to-end tests for the session authentication middleware."""

    async def test_request_without_session(self, client: TestClient):
        """Should result in AnonymousUser when no session is present."""
        response = client.get("/me")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] is None
        assert data["username"] == AnonymousUser().username

    async def test_request_with_valid_session(
        self, client: TestClient, test_user: User, db_session: AsyncSession
    ):
        """Should authenticate the user when a valid session is in scope."""
        session = UserSession(
            user_id=test_user.id,
            ip_address="127.0.0.1",
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        client.post(f"/force_session/{session.session_key}")
        response = client.get("/me")

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == test_user.username
        assert data["user_id"] == test_user.id

    async def test_request_with_invalid_token(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ):
        """Should result in AnonymousUser when session token is invalid."""
        logger = logging.getLogger("flash_authentication_session.middleware")
        logger.setLevel(logging.DEBUG)

        client.post("/force_session/invalid_123")

        with caplog.at_level(
            logging.DEBUG, logger="flash_authentication_session.middleware"
        ):
            response = client.get("/me")

            assert response.status_code == 200
            data = response.json()
            assert data["username"] == AnonymousUser().username
            assert "Authentication failed for token ending in ..._123" in caplog.text

    async def test_request_with_expired_session(
        self, client: TestClient, test_user: User, db_session: AsyncSession
    ):
        """Should result in AnonymousUser when the session has expired."""
        session = UserSession(
            user_id=test_user.id,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(session)
        await db_session.commit()

        client.post(f"/force_session/{session.session_key}")
        response = client.get("/me")

        assert response.status_code == 200
        assert response.json()["username"] == AnonymousUser().username

    async def test_db_error_handling(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ):
        """Should catch and log database errors during authentication."""
        with (
            unittest.mock.patch(
                "flash_authentication_session.middleware.SessionAuthenticationBackend.authenticate",
                side_effect=Exception("DB Fail"),
            ),
            caplog.at_level(
                logging.ERROR, logger="flash_authentication_session.middleware"
            ),
        ):
            client.post("/force_session/any_token")
            response = client.get("/me")

            assert response.status_code == 200
            assert response.json()["username"] == AnonymousUser().username
            assert (
                "Authentication middleware encountered an unexpected error"
                in caplog.text
            )

    async def test_authentication_success_expunge_model(self):
        """Should expunge the user from DB session on successful authentication."""
        mock_db = unittest.mock.AsyncMock(spec=AsyncSession)
        mock_factory = unittest.mock.MagicMock()
        mock_factory.return_value.__aenter__.return_value = mock_db
        mock_factory.return_value.__aexit__.return_value = None

        mock_user = unittest.mock.MagicMock(spec=Model)
        auth_result = AuthenticationResult(
            success=True,
            user=mock_user,
            message="Success",
            extra={"session": "session_obj"},
        )

        middleware = SessionAuthenticationMiddleware(
            unittest.mock.AsyncMock(), session_maker=mock_factory
        )

        with unittest.mock.patch.object(
            middleware.backend, "authenticate", return_value=auth_result
        ):
            scope = {
                "type": "http",
                "session": {SESSION_COOKIE_NAME: "token"},
            }
            receive = unittest.mock.AsyncMock()
            send = unittest.mock.AsyncMock()
            await middleware(scope, receive, send)
            mock_db.expunge.assert_called_once_with(mock_user)

    async def test_lifespan_scope_ignored(self, db_session: AsyncSession):  # noqa: ARG002
        """Should pass through non-HTTP/WebSocket scopes without authentication."""
        app_called = False

        async def mock_app(scope, receive, send):  # noqa: ARG001
            nonlocal app_called
            app_called = True

        factory = db_module._require_session_factory()
        middleware = SessionAuthenticationMiddleware(mock_app, session_maker=factory)

        scope = {"type": "lifespan"}
        receive = unittest.mock.AsyncMock()
        send = unittest.mock.AsyncMock()
        await middleware(scope, receive, send)
        assert app_called
        assert "state" not in scope
