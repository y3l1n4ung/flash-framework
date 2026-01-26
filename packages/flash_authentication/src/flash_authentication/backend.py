from abc import ABC, abstractmethod
from typing import Any

from .schemas import AuthenticationResult


class AuthenticationBackend(ABC):
    @abstractmethod
    async def authenticate(self, *arg: Any, **kwargs: Any) -> AuthenticationResult: ...

    @abstractmethod
    async def login(self, *arg: Any, **kwargs: Any) -> AuthenticationResult: ...

    @abstractmethod
    async def logout(self, *arg: Any, **kwargs: Any) -> Any: ...
