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

    Error Handling:
        - RuntimeError: Database session not available
        - HTTPException(404): Empty results and allow_empty=False
        - HTTPException(503): Database connection unavailable
        - HTTPException(500): Database integrity or unknown error
    """

    model: type[T]
    queryset: QuerySet[T] | None = None
    db: AsyncSession | None = None
    paginate_by: int | None = None
    ordering: str | list[str] | None = None
    allow_empty: bool = True

    def __init_subclass__(cls) -> None:
        from flash_db.validator import ModelValidator

        model = getattr(cls, "model", None)
        base_classes = ("ListView",)

        if model is None and cls.__name__ not in base_classes:
            msg = (
                f"The '{cls.__name__}' is missing the required 'model' attribute. "
                f"Usage: class {cls.__name__}(MultipleObjectMixin): "
                f"model = MyModelClass"
            )
            raise TypeError(msg)

        if model is not None:
            try:
                ModelValidator.validate_model(model)
            except TypeError as e:
                raise TypeError(str(e)) from e

        return super().__init_subclass__()

    def get_queryset(self) -> QuerySet[T]:
        if self.queryset is not None:
            return self.queryset
        return self.model.objects.all()

    @staticmethod
    def resolve_ordering(
        params_ordering: List[OrderingInstruction] | None = None,
        class_ordering: str | list[str] | None = None,
    ) -> List[OrderingInstruction]:
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

        return normalized

    async def get_objects(
        self,
        limit: int | None = None,
        offset: int = 0,
        ordering: List[OrderingInstruction] | None = None,
        *,
        auto_error: bool = True,
    ) -> dict[str, Any]:
        if self.db is None:
            msg = "Database session is required but not set."
            raise RuntimeError(msg)

        qs = self.get_queryset()

        # Apply ordering
        ordering_map = self.resolve_ordering(ordering, self.ordering)
        for field, direction in ordering_map:
            if hasattr(self.model, field):
                col = getattr(self.model, field)
                qs = qs.order_by(col.desc() if direction == "desc" else col.asc())
            else:
                logger.warning(
                    "Model %s has no field '%s'.",
                    self.model.__name__,
                    field,
                )

        effective_limit = limit or self.paginate_by

        try:
            total_count = await qs.count(self.db)

            if effective_limit:
                qs = qs.limit(effective_limit).offset(offset)

            object_list = await qs.fetch(self.db)

        except OperationalError as e:
            logger.exception("Database connection error")
            raise HTTPException(
                status_code=503,
                detail="Database service temporarily unavailable.",
            ) from e
        except (IntegrityError, DatabaseError) as e:
            logger.exception("Database error")
            raise HTTPException(
                status_code=500,
                detail="Internal database error occurred.",
            ) from e
        except Exception as e:
            logger.exception("Unexpected error")
            raise HTTPException(status_code=500, detail="Internal server error") from e

        if not object_list and not self.allow_empty and auto_error:
            raise HTTPException(
                status_code=404,
                detail=f"No {self.model.__name__} objects found.",
            )

        has_next = False
        if effective_limit and len(object_list) >= effective_limit:
            has_next = total_count > offset + effective_limit

        return {
            "object_list": object_list,
            "total_count": total_count,
            "limit": effective_limit,
            "offset": offset,
            "has_next": has_next,
            "has_previous": offset > 0,
        }
