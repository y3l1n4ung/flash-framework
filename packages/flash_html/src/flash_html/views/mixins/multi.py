import logging
from typing import Any, Generic, List, Literal, Tuple, TypeVar

from fastapi import HTTPException
from flash_db.models import Model
from flash_db.queryset import QuerySet
from sqlalchemy.exc import (
    DatabaseError,
    IntegrityError,
    OperationalError,
)
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Model)

SortDirection = Literal["asc", "desc"]
OrderingInstruction = Tuple[str, SortDirection]


class MultipleObjectMixin(Generic[T]):
    """
    Retrieve multiple objects from the database.

    Provides query building, ordering, and pagination for list views.

    Attributes:
        model: The database model class. Required.
        queryset: Custom queryset override.
        db: SQLAlchemy async session.
        paginate_by: Default page size.
        ordering: Default sort order (e.g., "-id").
        allow_empty: If False, raise 404 on empty results.

    Examples:
        >>> class ProductMixin(MultipleObjectMixin[Product]):
        ...     model = Product
        ...     paginate_by = 20
        ...     ordering = "-created_date"
        ...
        >>> mixin = ProductMixin()
        >>> mixin.db = session
        >>> data = await mixin.get_objects(limit=10, offset=0)
        >>> print(data["total_count"], len(data["object_list"]))
        42 10
    """

    model: type[T]
    queryset: QuerySet[T] | None = None
    db: AsyncSession | None = None
    paginate_by: int | None = None
    ordering: str | list[str] | None = None
    allow_empty: bool = True

    def __init_subclass__(cls) -> None:
        """Validate model attribute on subclass creation.

        Raises TypeError if subclass requires model but doesn't have it.

        Examples:
            >>> class ProductList(MultipleObjectMixin):
            ...     model = Product  # Required
            >>> # No error raised

            >>> class InvalidList(MultipleObjectMixin):
            ...     pass  # Missing model
            >>> # TypeError: missing required 'model' attribute
        """
        from flash_db.validator import ModelValidator

        model = getattr(cls, "model", None)
        base_classes = ("ListView",)

        if model is None and cls.__name__ not in base_classes:
            raise TypeError(
                f"The '{cls.__name__}' is missing the required 'model' attribute. "
                f"Usage: class {cls.__name__}(MultipleObjectMixin): model = MyModelClass"
            )

        if model is not None:
            try:
                ModelValidator.validate_model(model)
            except TypeError as e:
                raise TypeError(str(e)) from e

        return super().__init_subclass__()

    def get_queryset(self) -> QuerySet[T]:
        """Return base queryset for the model.

        Override to add custom filters or select_related.

        Returns:
            QuerySet: Base query or custom queryset.

        Examples:
            >>> class ProductMixin(MultipleObjectMixin):
            ...     model = Product
            ...     def get_queryset(self):
            ...         return self.model.objects.filter(published=True)
            >>> mixin = ProductMixin()
            >>> qs = mixin.get_queryset()
        """
        if self.queryset is not None:
            return self.queryset
        return self.model.objects.all()

    @staticmethod
    def resolve_ordering(
        params_ordering: List[OrderingInstruction] | None = None,
        class_ordering: str | list[str] | None = None,
    ) -> List[OrderingInstruction]:
        """Normalize and resolve ordering parameters.

        Params ordering takes priority over class ordering.
        Converts string format "-field" to ("field", "desc") tuples.

        Args:
            params_ordering: Ordering from request (highest priority).
            class_ordering: Default ordering from class.

        Returns:
            List of (field, direction) tuples.

        Examples:
            >>> MultipleObjectMixin.resolve_ordering(None, "-name")
            [('name', 'desc')]

            >>> MultipleObjectMixin.resolve_ordering(None, ["id", "-created"])
            [('id', 'asc'), ('created', 'desc')]

            >>> MultipleObjectMixin.resolve_ordering(
            ...     [("priority", "desc")], "-id"
            ... )
            [('priority', 'desc')]
        """
        raw = params_ordering if params_ordering is not None else class_ordering
        if not raw:
            return []

        items = [raw] if isinstance(raw, str) else raw
        normalized: List[OrderingInstruction] = []

        for item in items:
            if isinstance(item, tuple):
                normalized.append(item)
            elif isinstance(item, str):
                if item.startswith("-"):
                    normalized.append((item[1:], "desc"))
                else:
                    normalized.append((item, "asc"))

        logger.debug(f"Resolved ordering: {normalized}")
        return normalized

    async def get_objects(
        self,
        limit: int | None = None,
        offset: int = 0,
        ordering: List[OrderingInstruction] | None = None,
        auto_error: bool = True,
    ) -> dict[str, Any]:
        """Fetch paginated objects from database.

        Applies ordering, counts total results, applies pagination,
        and returns objects with metadata.

        Args:
            limit: Items per page. Uses paginate_by if not provided.
            offset: Number of items to skip.
            ordering: List of (field, direction) tuples for sorting.
            auto_error: Raise 404 if empty and allow_empty=False.

        Returns:
            Dictionary with:
                - object_list: List of model instances
                - total_count: Total matching objects (before pagination)
                - limit: Applied limit
                - offset: Applied offset
                - has_next: Whether next page exists
                - has_previous: Whether previous page exists

        Raises:
            RuntimeError: Database session not assigned.
            HTTPException(404): Empty results and allow_empty=False.
            HTTPException(503): Database connection unavailable.
            HTTPException(500): Database integrity or unknown error.

        Examples:
            >>> class ProductMixin(MultipleObjectMixin[Product]):
            ...     model = Product
            ...     paginate_by = 20
            ...
            >>> mixin = ProductMixin()
            >>> mixin.db = session
            >>> data = await mixin.get_objects(limit=10, offset=0)
            >>> data["total_count"]
            42
            >>> len(data["object_list"])
            10
            >>> data["has_next"]
            True

            >>> # With ordering
            >>> data = await mixin.get_objects(
            ...     limit=5,
            ...     offset=0,
            ...     ordering=[("name", "asc"), ("id", "desc")]
            ... )

            >>> # Without limit (uses paginate_by)
            >>> data = await mixin.get_objects(offset=20)
            >>> len(data["object_list"])
            20
        """
        if self.db is None:
            raise RuntimeError(
                "Database session is required but not set. "
                "Ensure your view is using Depends(get_db) for 'db' parameter."
            )

        try:
            qs = self.get_queryset()
            logger.debug(f"Fetching {self.model.__name__} objects")

            # Apply ordering
            ordering_map = self.resolve_ordering(ordering, self.ordering)
            for field, direction in ordering_map:
                if hasattr(self.model, field):
                    col = getattr(self.model, field)
                    qs = qs.order_by(col.desc() if direction == "desc" else col.asc())
                    logger.debug(f"Applied ordering: {field} {direction}")
                else:
                    logger.warning(
                        f"Model {self.model.__name__} has no field '{field}'. Skipping."
                    )

            # Get total count before pagination
            total_count = await qs.count(self.db)
            logger.debug(f"Total count: {total_count}")

            # Apply pagination
            effective_limit = limit or self.paginate_by
            if effective_limit:
                qs = qs.limit(effective_limit).offset(offset)
                logger.debug(f"Pagination: limit={effective_limit}, offset={offset}")

            # Fetch objects
            object_list = await qs.fetch(self.db)
            logger.debug(f"Fetched {len(object_list)} objects")

            # Check if empty and not allowed
            if not object_list and not self.allow_empty and auto_error:
                logger.info(f"Empty {self.model.__name__} list not allowed")
                raise HTTPException(
                    status_code=404,
                    detail=f"No {self.model.__name__} objects found.",
                )

            # Calculate pagination metadata
            has_next = False
            has_previous = offset > 0
            if effective_limit and len(object_list) >= effective_limit:
                has_next = total_count > offset + effective_limit

            return {
                "object_list": object_list,
                "total_count": total_count,
                "limit": effective_limit,
                "offset": offset,
                "has_next": has_next,
                "has_previous": has_previous,
            }
        except HTTPException:
            raise

        except OperationalError as e:
            logger.exception(
                f"Database connection error while fetching {self.model.__name__} list"
            )
            raise HTTPException(
                status_code=503,
                detail="Database service temporarily unavailable. Please try again later.",
            ) from e

        except IntegrityError as e:
            logger.exception(
                f"Database integrity error while fetching {self.model.__name__} list"
            )
            raise HTTPException(
                status_code=500,
                detail="Database integrity error. Please contact support.",
            ) from e

        except DatabaseError as e:
            logger.exception(
                f"Database error while fetching {self.model.__name__} list: {e}"
            )
            raise HTTPException(
                status_code=500, detail="Database error. Please try again later."
            ) from e

        except Exception as e:
            logger.exception(
                f"Unexpected error fetching {self.model.__name__} list: {type(e).__name__}"
            )
            raise HTTPException(status_code=500, detail="Internal server error") from e
