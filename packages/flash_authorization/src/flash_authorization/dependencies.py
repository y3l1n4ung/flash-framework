from typing import cast

from fastapi import Depends, HTTPException, Request, status
from flash_authentication import AnonymousUser, User

from .permissions import (
    AllowAny,
    BasePermission,
    IsAuthenticated,
    IsStaffUser,
    IsSuperUser,
)


class PermissionRedirectError(Exception):
    """Signal used to trigger a redirect when permissions fail."""

    def __init__(self, url: str):
        self.url = url


def get_current_user(request: Request):
    if request.state.user is None:
        return AnonymousUser()
    return cast("User", request.state.user)


async def handle_permission_denied(
    request: Request,
    *,
    user: User | AnonymousUser,
    login_url: str | None = None,
    redirect_field_name: str = "next",
    raise_exception: bool = False,
):
    if raise_exception:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action",
        )
    if not user.is_active and login_url:
        path = request.url.path
        query = request.url.query
        full_path = f"{path}?{query}" if query else path
        sep = "&" if "?" in login_url else "?"
        redirect_url = f"{login_url}{sep}{redirect_field_name}={full_path}"
        raise PermissionRedirectError(redirect_url)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to perform this action",
    )


def permission_dependency(
    permissions: list[BasePermission],
    *,
    login_url: str | None = None,
    redirect_field_name: str = "next",
    raise_exception: bool = False,
):
    """FastAPI dependency factory for checking permissions.


    Args:
        permissions (list[BasePermission]): A list of permissions to check.
    """

    async def permission_dependency_factory(
        request: Request, user: User | AnonymousUser = Depends(get_current_user)
    ):
        for permission in permissions:
            if not await permission.has_permission(request, user):
                await handle_permission_denied(
                    request,
                    user=user,
                    login_url=login_url,
                    redirect_field_name=redirect_field_name,
                    raise_exception=raise_exception,
                )
        return user

    return permission_dependency_factory


allow_any = permission_dependency([AllowAny()])
auth_required = permission_dependency([IsAuthenticated()])
is_superuser = permission_dependency([IsSuperUser()])
is_staff_user = permission_dependency([IsStaffUser()])
