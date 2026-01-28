import os
from typing import Any, override

from flash_authentication import AuthenticationBackend
from flash_authentication.schemas import (
    AuthenticationResult,
)
from sqlalchemy.ext.asyncio import AsyncSession

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "session")

DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")


class SessionAuthenticationBackend(AuthenticationBackend):
    @override
    async def authenticate(
        self,
        db: AsyncSession,
        session_token: str,
    ) -> AuthenticationResult:
        raise NotImplementedError

    async def login(self, *arg: Any, **kwargs: Any) -> AuthenticationResult:
        raise NotImplementedError

    async def logout(self, *arg: Any, **kwargs: Any) -> Any:
        raise NotImplementedError
