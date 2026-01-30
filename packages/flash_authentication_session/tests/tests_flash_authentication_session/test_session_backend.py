from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Request
from flash_authentication.models import User
from flash_authentication_session.backend import (
    SESSION_COOKIE_NAME,
    SessionAuthenticationBackend,
)
from flash_authentication_session.models import UserSession
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
class TestSessionBackendUnit:
    """
    Unit tests for SessionAuthenticationBackend methods.

    """

    def _create_request(
        self,
        session_data: dict | None = None,
        headers: list | None = None,
    ) -> Request:
        """Helper to create a real Starlette/FastAPI Request with a session scope."""
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/",
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": headers or [],
            "client": ("127.0.0.1", 12345),
            # SessionMiddleware usually populates this.
            # We populate it manually for unit testing.
            "session": session_data if session_data is not None else {},
        }
        return Request(scope)

    async def test_login_success(
        self,
        backend: SessionAuthenticationBackend,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test backend.login stores session in DB and updates request.session."""
        request = self._create_request()

        result = await backend.login(
            request,
            db_session,
            username=test_user.username,
            email=None,
            password="password123",
        )

        # 1. Check Result
        assert result.success is True
        assert result.user.id == test_user.id

        # 2. Check Request Session (Cookie) was set
        assert SESSION_COOKIE_NAME in request.session
        session_key = request.session[SESSION_COOKIE_NAME]
        assert session_key is not None

        # 3. Check DB Persistence
        stmt = select(UserSession).where(UserSession.session_key == session_key)
        stored_session = await db_session.scalar(stmt)
        assert stored_session is not None
        assert stored_session.user_id == test_user.id
        assert stored_session.ip_address == "127.0.0.1"

    async def test_login_invalid_password(
        self,
        backend: SessionAuthenticationBackend,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test login fails with incorrect password."""
        request = self._create_request()

        result = await backend.login(
            request,
            db_session,
            username=test_user.username,
            email=None,
            password="wrongpassword",
        )

        assert result.success is False
        assert result.message == "Login Failed"
        assert SESSION_COOKIE_NAME not in request.session

    async def test_login_inactive_user(
        self,
        backend: SessionAuthenticationBackend,
        db_session: AsyncSession,
        inactive_test_user: User,
    ) -> None:
        """Test login fails for inactive user."""
        request = self._create_request()

        result = await backend.login(
            request,
            db_session,
            username=inactive_test_user.username,
            email=None,
            password="password123",
        )

        assert result.success is False
        assert "inactive" in result.errors[0]
        assert SESSION_COOKIE_NAME not in request.session

    async def test_login_missing_session_middleware(
        self,
        backend: SessionAuthenticationBackend,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test login fails gracefully if SessionMiddleware is not installed
        (missing 'session' in scope)."""
        # Create request manually without "session" key in scope
        scope = {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            # Missing "session" key
        }
        request = Request(scope)

        result = await backend.login(
            request,
            db_session,
            username=test_user.username,
            email=None,
            password="password123",
        )

        assert result.success is False
        assert result.message == "Configuration Error"
        assert "SessionMiddleware" in result.errors[0]

    async def test_login_database_error(
        self,
        backend: SessionAuthenticationBackend,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test login handles database exceptions gracefully."""
        request = self._create_request()

        # force raising error on commit
        async def raising_commit():
            msg = "Forced DB Error"
            raise RuntimeError(msg)

        db_session.commit = raising_commit  # ty:ignore[invalid-assignment]

        result = await backend.login(
            request,
            db_session,
            username=test_user.username,
            email=None,
            password="password123",
        )

        assert result.success is False
        assert result.message == "Login Failed"
        # Checks that the exception message was captured in errors
        assert len(result.errors) > 0

    async def test_authenticate_valid_session(
        self,
        backend: SessionAuthenticationBackend,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test authenticate retrieves user from valid session token."""
        # Setup: Create a session manually
        session = UserSession(
            user_id=test_user.id,
            ip_address="1.1.1.1",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        # Execute
        result = await backend.authenticate(db_session, session.session_key)

        assert result.success is True
        assert result.user.id == test_user.id
        assert result.extra["session"].session_key == session.session_key

    async def test_authenticate_expired_session(
        self,
        backend: SessionAuthenticationBackend,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test authenticate rejects an expired session."""
        # Setup: Create a session that expired 1 hour ago
        session = UserSession(
            user_id=test_user.id,
            ip_address="1.1.1.1",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        # Execute
        result = await backend.authenticate(db_session, session.session_key)

        assert result.success is False
        assert result.message == "Session Expired"

    async def test_authenticate_invalid_token(
        self, backend: SessionAuthenticationBackend, db_session: AsyncSession
    ) -> None:
        """Test authenticate fails with non-existent token."""
        result = await backend.authenticate(db_session, "invalid_token_string")

        assert result.success is False
        assert result.message == "Invalid Session"

    async def test_authenticate_missing_dependencies(
        self, backend: SessionAuthenticationBackend, db_session: AsyncSession
    ) -> None:
        """Test authenticate handles missing token."""
        # Case 1: Missing Token
        result_no_token = await backend.authenticate(db_session, "")
        assert result_no_token.success is False
        assert result_no_token.message == "Internal Error"

    async def test_authenticate_inactive_user(
        self,
        backend: SessionAuthenticationBackend,
        db_session: AsyncSession,
        inactive_test_user: User,
    ) -> None:
        """Test authenticate refuses session for inactive user."""
        session = UserSession(
            user_id=inactive_test_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add(session)
        await db_session.commit()

        result = await backend.authenticate(db_session, session.session_key)

        assert result.success is False
        assert result.message == "Account Inactive"

    async def test_logout_success(
        self,
        backend: SessionAuthenticationBackend,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test logout removes session from DB and request."""
        # Setup
        session = UserSession(
            user_id=test_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        # Create request with the session key
        request = self._create_request(
            session_data={SESSION_COOKIE_NAME: session.session_key}
        )

        # Execute
        success = await backend.logout(request, db_session)

        assert success is True
        assert len(request.session) == 0  # Session dict should be cleared

        # Verify DB deletion
        stmt = (
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.session_key == session.session_key)
        )
        count = await db_session.scalar(stmt)
        assert count == 0

    async def test_logout_no_session(
        self, backend: SessionAuthenticationBackend, db_session: AsyncSession
    ) -> None:
        """Test logout returns False if request has no session dict
        (middleware present but empty session)."""
        request = self._create_request(session_data={})

        success = await backend.logout(request, db_session)

        assert success is False

    async def test_logout_missing_session_middleware(
        self, backend: SessionAuthenticationBackend, db_session: AsyncSession
    ) -> None:
        """Test logout returns False if SessionMiddleware is missing
        (no 'session' in scope)."""
        # Create request manually without "session" key in scope
        scope = {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            # Missing "session" key
        }
        request = Request(scope)

        success = await backend.logout(request, db_session)

        assert success is False

    async def test_logout_database_error(
        self,
        backend: SessionAuthenticationBackend,
        db_session: AsyncSession,
        test_user: User,
    ) -> None:
        """Test logout handles database exceptions gracefully."""
        # Setup session
        session = UserSession(
            user_id=test_user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add(session)
        await db_session.commit()
        await db_session.refresh(session)

        request = self._create_request(
            session_data={SESSION_COOKIE_NAME: session.session_key}
        )

        # Force error on commit
        async def raising_commit():
            msg = "Forced DB Error"
            raise RuntimeError(msg)

        db_session.commit = raising_commit  # ty:ignore[invalid-assignment]

        success = await backend.logout(request, db_session)

        assert success is False

    def test_get_client_info_extraction(
        self, backend: SessionAuthenticationBackend
    ) -> None:
        """Test IP extraction from headers without mocks."""
        # 1. Direct
        req1 = self._create_request()
        ip, _agent = backend._get_client_info(req1)
        assert ip == "127.0.0.1"

        # 2. Proxy (X-Forwarded-For)
        headers = [
            (b"x-forwarded-for", b"10.0.0.5, 127.0.0.1"),
            (b"user-agent", b"TestAgent"),
        ]
        req2 = self._create_request(headers=headers)

        ip2, agent2 = backend._get_client_info(req2)
        assert ip2 == "10.0.0.5"
        assert agent2 == "TestAgent"
