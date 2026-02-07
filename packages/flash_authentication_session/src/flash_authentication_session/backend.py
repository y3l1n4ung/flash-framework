import os
from datetime import datetime, timedelta, timezone
from typing import Any, override

from fastapi import Request
from flash_authentication import AnonymousUser, AuthenticationBackend
from flash_authentication.models import User
from flash_authentication.schemas import (
    AuthenticationResult,
)
from sqlalchemy import false, or_
from sqlalchemy.ext.asyncio import AsyncSession

from flash_authentication_session.models import UserSession

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "session")

DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
# Default to 2 weeks (1,209,600 seconds) if not specified
SESSION_EXPIRE_SECONDS = int(
    os.getenv("SESSION_EXPIRE_SECONDS", str(14 * 24 * 60 * 60))
)


class SessionAuthenticationBackend(AuthenticationBackend):
    @override
    async def authenticate(
        self,
        db: AsyncSession,
        session_token: str,
    ) -> AuthenticationResult:
        """Verify the session key from the cookie against the database.

        Args:
            session_token (str): The session key token.
            db (AsyncSession): Database session.

        Returns:
            AuthenticationResult: Always returns a result object, never None.

        """
        if not session_token or not db:
            return AuthenticationResult(
                success=False,
                user=AnonymousUser(),
                message="Internal Error",
                errors=["Missing 'token' or 'db' dependency"],
            )

        user_session = (
            await UserSession.objects.select_related("user")
            .filter(UserSession.session_key == session_token)
            .first(db)
        )

        if not user_session:
            return AuthenticationResult(
                success=False,
                user=AnonymousUser(),
                message="Invalid Session",
                errors=["Session key does not exist in database"],
            )

        user = user_session.user

        if not user.is_active:
            return AuthenticationResult(
                success=False,
                user=user,
                message="Account Inactive",
                errors=["User account is disabled"],
            )
        if user_session.is_expired:
            return AuthenticationResult(
                success=False,
                user=AnonymousUser(),
                message="Session Expired",
                errors=["The session has expired"],
            )

        return AuthenticationResult(
            success=True,
            user=user,
            message="Authenticated",
            extra={
                "session": user_session,
            },
        )

    @override
    async def login(
        self,
        request: Request,
        db: AsyncSession,
        *,
        username: str | None,
        email: str | None,
        password: str,
    ) -> AuthenticationResult:
        if "session" not in request.scope:
            return AuthenticationResult(
                success=False,
                user=AnonymousUser(),
                message="Configuration Error",
                errors=["SessionMiddleware not installed"],
            )
        user = None
        if password and (username or email):
            user = await User.objects.filter(
                or_(
                    (User.username == username) if username else false(),
                    (User.email == email) if email else false(),
                )
            ).first(db)

            if user and not user.check_password(password):
                user = None

        if not user:
            return AuthenticationResult(
                success=False,
                user=AnonymousUser(),
                message="Login Failed",
                errors=["Invalid credentials"],
            )
        if not user.is_active:
            return AuthenticationResult(
                success=False,
                user=user,
                message="Login Failed",
                errors=["Account is inactive"],
            )
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=SESSION_EXPIRE_SECONDS
        )
        ip_address, user_agent = self._get_client_info(request)

        try:
            user_session = await UserSession.objects.create(
                db,
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                expires_at=expires_at,
            )
            await db.commit()

            request.session[SESSION_COOKIE_NAME] = user_session.session_key
            return AuthenticationResult(
                success=True,
                user=user,
                message="Login Successful",
                extra={"session_key": user_session.session_key},
            )
        except Exception as e:
            await db.rollback()
            return AuthenticationResult(
                success=False,
                user=AnonymousUser(),
                message="Login Failed",
                errors=[str(e)],
            )

    @override
    async def logout(
        self,
        request: Request,
        db: AsyncSession,
    ) -> Any:
        if "session" not in request.scope:
            return False
        session_key = request.session.get(SESSION_COOKIE_NAME)
        if not session_key:
            return False
        try:
            await UserSession.objects.filter(
                UserSession.session_key == session_key
            ).delete(db)
            await db.commit()
            request.session.clear()

        except Exception:
            await db.rollback()
            return False
        return True

    def _get_client_info(self, request: Request) -> tuple[str | None, str | None]:
        """Extract client IP and user agent from request headers."""
        # Handle Proxy Headers for IP extraction
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            ip_address = forwarded.split(",")[0].strip()
        else:
            ip_address = request.client.host if request.client else None

        user_agent = request.headers.get("user-agent")
        return ip_address, user_agent
