from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from fastapi import Request
from flash_authentication.models import User
from flash_authentication.schemas import AnonymousUser
from flash_db import Model

T = TypeVar("T", bound=Model)


class BasePermission(ABC, Generic[T]):
    @abstractmethod
    async def has_permission(
        self, request: Request, user: User | AnonymousUser
    ) -> bool:
        raise NotImplementedError

    async def has_object_permission(
        self,
        request: Request,  # noqa: ARG002
        obj: T,  # noqa: ARG002
        user: User | AnonymousUser,  # noqa: ARG002
    ) -> bool:
        return True


class AllowAny(BasePermission):
    """Allow access to anyone (authenticated or not)."""

    async def has_permission(
        self,
        request: Request,  # noqa: ARG002
        user: User | AnonymousUser,  # noqa: ARG002
    ):
        return True


class IsAuthenticated(BasePermission):
    """Allow access only to authenticated users."""

    async def has_permission(
        self,
        request: Request,  # noqa: ARG002
        user: User | AnonymousUser,
    ):
        return user.is_active


class IsStaffUser(BasePermission):
    """Allow access only to staff users."""

    async def has_permission(
        self,
        request: Request,  # noqa: ARG002
        user: User | AnonymousUser,
    ):
        return user.is_staff


class IsSuperUser(BasePermission):
    """Allow access only to super users."""

    async def has_permission(
        self,
        request: Request,  # noqa: ARG002
        user: User | AnonymousUser,
    ):
        return user.is_superuser


class ReadOnly(BasePermission):
    """Allow read only access (GET, HEAD, OPTIONS)"""

    async def has_permission(
        self,
        request: Request,
        user: User | AnonymousUser,  # noqa: ARG002
    ):
        return request.method in ["GET", "HEAD", "OPTIONS"]


class IsAuthenticatedOrReadOnly(BasePermission):
    """Allow read-only access to anyone, write access to authenticated users."""

    async def has_permission(
        self, request: Request, user: User | AnonymousUser
    ) -> bool:
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return True
        return user.is_active
