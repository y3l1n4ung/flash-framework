from fastapi import Depends, Request
from flash_authentication.schemas import AnonymousUser, AuthenticationResult
from flash_db import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from .backend import SESSION_COOKIE_NAME, SessionAuthenticationBackend


async def get_user_from_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthenticationResult:
    backend = SessionAuthenticationBackend()
    if "session" not in request.scope:
        return AuthenticationResult(
            success=False,
            user=AnonymousUser(),
            message="Configuration Error: SessionMiddleware not installed",
            errors=["Request scope missing 'session' key"],
        )
    token = request.session.get(SESSION_COOKIE_NAME, "")
    return await backend.authenticate(db, token)
