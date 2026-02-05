from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from flash_authentication.models import User
from flash_authentication_session.backend import (
    SESSION_COOKIE_NAME,
    SessionAuthenticationBackend,
)
from flash_authentication_session.models import UserSession
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class TestSessionBackend:
    """Integration tests for the Session Authentication Backend."""

    def test_login_flow_success(self, client: TestClient, test_user: User) -> None:
        """Verifies complete login lifecycle: credentials -> session -> cookie -> DB."""
        # 1. Login
        response = client.post(
            "/login", json={"username": test_user.username, "password": "password123"}
        )

        assert response.status_code == 200
        assert response.json()["user"] == test_user.id

        # 2. Verify Signed Cookie
        assert SESSION_COOKIE_NAME in client.cookies

        # 3. Verify Session Persistence via Protected Route
        verify_response = client.get("/verify")
        assert verify_response.status_code == 200
        assert verify_response.json()["user_id"] == test_user.id

    def test_login_invalid_credentials(
        self, client: TestClient, test_user: User
    ) -> None:
        """Ensures login fails and no cookie is set for incorrect passwords."""
        response = client.post(
            "/login", json={"username": test_user.username, "password": "wrongpassword"}
        )

        assert response.status_code == 401
        assert "Login Failed" in response.json()["detail"]
        assert SESSION_COOKIE_NAME not in client.cookies

    def test_login_empty_credentials(self, client: TestClient) -> None:
        """Ensures login rejects empty strings for mandatory fields."""
        response = client.post("/login", json={"username": "", "password": ""})

        assert response.status_code == 401
        assert SESSION_COOKIE_NAME not in client.cookies

    def test_login_missing_payload(self, client: TestClient) -> None:
        """Ensures backend handles missing fields gracefully (401 or handled error)."""
        # Missing 'password' field entirely
        response = client.post("/login", json={"username": "someone"})

        # Based on test_app route: payload.get("password") ->
        # None -> backend.login -> 401
        assert response.status_code == 401
        assert SESSION_COOKIE_NAME not in client.cookies

    def test_login_inactive_user(
        self, client: TestClient, inactive_test_user: User
    ) -> None:
        """Ensures inactive users are denied access even with valid credentials."""
        response = client.post(
            "/login",
            json={"username": inactive_test_user.username, "password": "password123"},
        )

        assert response.status_code == 401
        assert SESSION_COOKIE_NAME not in client.cookies

    def test_multiple_sessions_same_user(
        self, client: TestClient, test_user: User
    ) -> None:
        """Verifies a user can maintain multiple active sessions
        (e.g., multiple devices).
        """
        # Login 1
        client.post(
            "/login", json={"username": test_user.username, "password": "password123"}
        )
        cookie_1 = client.cookies[SESSION_COOKIE_NAME]

        # Clear cookies to simulate new device context
        client.cookies.clear()

        # Login 2
        client.post(
            "/login", json={"username": test_user.username, "password": "password123"}
        )
        cookie_2 = client.cookies[SESSION_COOKIE_NAME]

        assert cookie_1 != cookie_2

        # Verify both sessions are valid by manually swapping cookies
        client.cookies.set(SESSION_COOKIE_NAME, cookie_1)
        assert client.get("/verify").status_code == 200

        client.cookies.set(SESSION_COOKIE_NAME, cookie_2)
        assert client.get("/verify").status_code == 200

    def test_logout_flow(self, client: TestClient, test_user: User) -> None:
        """Verifies logout clears the cookie and server-side session."""
        # Login
        client.post(
            "/login", json={"username": test_user.username, "password": "password123"}
        )

        # Logout
        logout_response = client.post("/logout")
        assert logout_response.status_code == 200
        assert logout_response.json()["success"] is True

        # Access Protected Route
        verify_response = client.get("/verify")
        assert verify_response.status_code == 401

    def test_logout_no_session(self, client: TestClient) -> None:
        """Verifies logout handles stateless/missing session requests gracefully."""
        response = client.post("/logout")
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_access_unauthorized(self, client: TestClient) -> None:
        """Ensures protected routes reject requests missing session cookies."""
        response = client.get("/verify")
        assert response.status_code == 401
        assert "No session token" in response.json()["detail"]

    def test_invalid_session_cookie(self, client: TestClient) -> None:
        """Ensures tampered or garbage cookies are rejected."""
        client.cookies.set(SESSION_COOKIE_NAME, "garbage_token_value")
        response = client.get("/verify")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_session_cascade_delete(
        self, client: TestClient, test_user: User, db_session: AsyncSession
    ) -> None:
        """Verifies that deleting a User cascades and removes their sessions from DB."""
        # 1. Login
        client.post(
            "/login", json={"username": test_user.username, "password": "password123"}
        )

        # 2. Verify Session Exists
        stmt = (
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.user_id == test_user.id)
        )
        count = await db_session.scalar(stmt)
        assert count == 1

        # 3. Delete User
        await db_session.delete(test_user)
        await db_session.commit()

        # 4. Verify Session Gone
        count_after = await db_session.scalar(stmt)
        assert count_after == 0

    @pytest.mark.asyncio
    async def test_session_expiry_enforcement(
        self, client: TestClient, test_user: User, db_session: AsyncSession
    ) -> None:
        """Verifies that the backend actively rejects expired sessions."""
        # Login
        client.post(
            "/login", json={"username": test_user.username, "password": "password123"}
        )

        # Manually expire session
        stmt = select(UserSession).where(UserSession.user_id == test_user.id)
        session_obj = await db_session.scalar(stmt)
        assert session_obj
        session_obj.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.add(session_obj)
        await db_session.commit()

        # Attempt Access
        response = client.get("/verify")
        assert response.status_code == 401

    def test_client_info_extraction_proxy(
        self, test_app: FastAPI, backend: SessionAuthenticationBackend
    ) -> None:
        """Verifies correct IP extraction from X-Forwarded-For headers."""

        @test_app.get("/debug_client")
        async def debug_client(request: Request):
            ip, agent = backend._get_client_info(request)
            return {"ip": ip, "agent": agent}

        client = TestClient(test_app)

        # 1. Direct Connection
        resp = client.get("/debug_client", headers={"User-Agent": "DirectAgent"})
        assert resp.json()["ip"] == "testclient"
        assert resp.json()["agent"] == "DirectAgent"

        # 2. Proxy Connection
        resp = client.get(
            "/debug_client",
            headers={
                "X-Forwarded-For": "10.0.0.5, 127.0.0.1",
                "User-Agent": "ProxyAgent",
            },
        )
        assert resp.json()["ip"] == "10.0.0.5"
        assert resp.json()["agent"] == "ProxyAgent"
