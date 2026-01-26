from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from fastapi import Request


class BaseUser(ABC):
    """Abstract interface for user entity.

    All user implementations (AbstractBaseUser, AnonymousUser) must
    implement this interface for type safety across authentication system.
    """

    @property
    @abstractmethod
    def is_authenticated(self) -> bool: ...
    @property
    @abstractmethod
    def display_name(self) -> str: ...


UserType = TypeVar("UserType", bound=BaseUser)


class BaseAuthenticator(ABC, Generic[UserType]):
    @abstractmethod
    async def authenticate(self, **kwargs: Any) -> UserType: ...


class BaseLoginBackend(ABC, Generic[UserType]):
    @abstractmethod
    async def login(self, request: Request, **kwarg: Any) -> Any: ...

    @abstractmethod
    async def logout(self, request: Request, **kwarg: Any) -> Any: ...
