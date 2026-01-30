from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Request
from flash_authentication_session.backend import SESSION_COOKIE_NAME
from flash_authentication_session.dependencies import get_user_from_session
from flash_authentication_session.models import UserSession


@pytest.mark.asyncio
class TestSessionDependencies:
    def _create_request_with_session(self, session_data: dict) -> Request:
        """Helper to create a request with a populated session scope."""
        scope = {"type": "http", "session": session_data}
        return Request(scope)

    async def test_get_user_from_session_valid(self, db_session, test_user):
        """Test retrieving a user with a valid session token."""
        # 1. Create valid session in DB
        user_session = UserSession(
            user_id=test_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db_session.add(user_session)
        await db_session.commit()

        # 2. Mock Request with session cookie
        req = self._create_request_with_session(
            {SESSION_COOKIE_NAME: user_session.session_key}
        )

        # 3. Call Dependency
        result = await get_user_from_session(req, db_session)

        # 4. Assert
        assert result.success is True
        assert result.user.id == test_user.id

    async def test_get_user_from_session_invalid_token(self, db_session):
        """Test retrieving a user with an invalid session token."""
        req = self._create_request_with_session({SESSION_COOKIE_NAME: "invalid_token"})

        result = await get_user_from_session(req, db_session)

        assert result.success is False
        assert result.message == "Invalid Session"

    async def test_get_user_from_session_missing_cookie(self, db_session):
        """Test retrieving a user when the session cookie is missing."""
        req = self._create_request_with_session({})  # Empty session

        result = await get_user_from_session(req, db_session)

        assert result.success is False
        assert (
            result.message == "Internal Error"
        )  # Backend returns this for empty/missing token

    async def test_get_user_from_session_missing_middleware(self, db_session):
        """Test handling when SessionMiddleware is missing (no session in scope)."""
        # Create request WITHOUT "session" in scope
        req = Request({"type": "http"})

        result = await get_user_from_session(req, db_session)

        assert result.success is False
        assert "SessionMiddleware not installed" in result.message
