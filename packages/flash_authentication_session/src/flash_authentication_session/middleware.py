import logging
from typing import Any, Awaitable, Callable, Final

from fastapi import Request
from flash_authentication.schemas import AnonymousUser
from flash_db.models import Model
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.types import ASGIApp

from .backend import SESSION_COOKIE_NAME, SessionAuthenticationBackend

logger = logging.getLogger(__name__)


class SessionAuthenticationMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        session_maker: async_sessionmaker[AsyncSession],
    ):
        self.app: Final[ASGIApp] = app
        self.backend: Final[SessionAuthenticationBackend] = (
            SessionAuthenticationBackend()
        )
        self.session_maker: Final[async_sessionmaker[AsyncSession]] = session_maker

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[Any]],
        send,
    ) -> Any:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return None
        request = Request(scope)

        request.state.user = AnonymousUser()
        request.state.auth = None

        try:
            token = request.cookies.get(SESSION_COOKIE_NAME, "")
            async with self.session_maker() as db:
                result = await self.backend.authenticate(db, token)

                if result.success:
                    user = result.user
                    if isinstance(user, Model):
                        db.expunge(user)
                    request.state.user = user
                    request.state.auth = result.extra.get("session")
                elif result.message:
                    logger.debug(
                        "Authentication failed for token ending in ...%s: %s",
                        token[-4:],
                        result.message,
                    )

        except Exception:
            logger.exception(
                "Authentication middleware encountered an unexpected error"
            )

        return await self.app(scope, receive, send)
