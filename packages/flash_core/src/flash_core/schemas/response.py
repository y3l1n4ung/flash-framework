"""
Core Pydantic schemas shared across modules.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound="BaseModel")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response model for the Flash ecosystem.

    Example:
        >>> from pydantic import BaseModel
        >>> class User(BaseModel):
        ...     id: int
        ...     username: str
        ...
        >>> # Create a type-safe paginated response for Users
        >>> data = PaginatedResponse[User](
        ...     items=[User(id=1, username="alex")],
        ...     total=100,
        ...     page=1,
        ...     limit=20
        ... )
        >>> data.total_pages
        5
        >>> data.model_dump()
        {
            'items': [{'id': 1, 'username': 'alex'}],
            'total': 100,
            'page': 1,
            'limit': 20,
            'total_pages': 5
        }
    """

    model_config = ConfigDict(from_attributes=True)

    items: list[T] = Field(..., description="List of items in current page")
    total: int = Field(..., description="Total number of items across all pages")
    limit: int = Field(default=50, description="Maximum items per page")
    offset: int = Field(default=0, description="Number of items to skip")
