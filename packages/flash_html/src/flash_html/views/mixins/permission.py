import inspect
from typing import Any, ClassVar, Protocol, runtime_checkable

from fastapi import Depends, HTTPException, Request, status
from flash_authentication import AnonymousUser, User
from flash_authorization.dependencies import permission_dependency
from flash_authorization.permissions import BasePermission
from flash_db import Model


@runtime_checkable
class ViewProtocol(Protocol):
    """
    Protocol defining the interface required by view mixins.

    Attributes:
        request (Request): The active FastAPI request instance.
    """

    request: Request

    @classmethod
    def resolve_dependencies(
        cls, params: list[inspect.Parameter], **kwargs: Any
    ) -> None:
        """
        Hook for dependency injection.

        Provides a default no-op implementation to ensure `super()` calls work
        safely in the Method Resolution Order (MRO).

        Args:
            params: A list of `inspect.Parameter` objects representing the
                view's signature.
            **kwargs: Arbitrary keyword arguments passed to `as_view`.
        """


class PermissionMixin(ViewProtocol):
    permission_classes: ClassVar[list[type[BasePermission]]] = []

    login_url: str | None = None  # URL to redirect to if user is unauthenticated
    redirect_field_name: str = "next"  # Query parameter name for the return URL
    raise_exception: bool = False  # If True, always 403 (don't redirect)

    @classmethod
    def resolve_dependencies(
        cls,
        params: list[inspect.Parameter],
        **kwargs: Any,
    ):
        perms_list = kwargs.get("permission_classes", cls.permission_classes)
        if perms_list:
            perms = [perm() for perm in perms_list]
            dep = permission_dependency(
                perms,
                login_url=kwargs.get("login_url", cls.login_url),
                redirect_field_name=kwargs.get(
                    "redirect_field_name", cls.redirect_field_name
                ),
                raise_exception=kwargs.get("raise_exception", cls.raise_exception),
            )
            params.insert(
                0,
                inspect.Parameter(
                    "_permissions",
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=Any,
                    default=Depends(dep),
                ),
            )

        super().resolve_dependencies(params, **kwargs)

    def get_permissions(self) -> list[BasePermission]:
        return [perm() for perm in self.permission_classes]

    async def check_object_permissions(
        self,
        request: Request,
        obj: Model,
        permissions: list[BasePermission],
        user: User | AnonymousUser,
    ):
        """Check object-level permissions manually."""
        for permission in permissions:
            if not await permission.has_object_permission(
                request,
                obj,
                user,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to perform this action",
                )
