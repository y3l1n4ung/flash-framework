"""
Custom permissions for DetailView example application.

Demonstrates how to create model-specific permissions.
"""

from fastapi import Request
from flash_authentication.models import User
from flash_authentication.schemas import AnonymousUser
from flash_authorization.permissions import BasePermission
from models import Article


class ArticleOwnerPermission(BasePermission):
    """
    Allow access only to the author of an article.

    This demonstrates how to create object-level permissions that check
    if the current user owns the specific object being accessed.
    """

    async def has_permission(
        self,
        request: Request,  # noqa: ARG002
        user: User | AnonymousUser,
    ) -> bool:
        """Check view-level permission - any active user can view."""
        return user.is_active

    async def has_object_permission(
        self,
        request: Request,  # noqa: ARG002
        obj: Article,
        user: User | AnonymousUser,
    ) -> bool:
        """
        Check object-level permission - only the article author can access.

        """
        return obj.author_id == user.id


class IsArticleAuthor(BasePermission):
    """
    Alternative implementation for article author permission.
    """

    async def has_permission(
        self,
        request: Request,  # noqa: ARG002
        user: User | AnonymousUser,
    ) -> bool:
        """Require active user."""
        return user.is_active

    async def has_object_permission(
        self,
        request: Request,  # noqa: ARG002
        obj: Article,
        user: User | AnonymousUser,
    ) -> bool:
        """Check if user is the article author."""
        return obj.author_id == user.id
