import logging
from typing import Any, Generic, TypeVar, cast

from fastapi import HTTPException
from flash_db.models import Model
from flash_db.queryset import QuerySet
from sqlalchemy.exc import (
    DatabaseError,
    IntegrityError,
    OperationalError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from .database import DatabaseMixin

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Model)


class SingleObjectMixin(DatabaseMixin, Generic[T]):
    """
    Retrieve a single object from the database.

    Error Handling:
        - RuntimeError: Database session not available
        - AttributeError: Missing URL parameter or field
        - HTTPException(404): Object not found (when auto_error=True)
        - HTTPException(503): Database unavailable
        - HTTPException(500): Database integrity or unknown error
    """

    model: type[T]
    queryset: QuerySet[T] | None = None
    db: AsyncSession | None = None
    slug_field: str = "slug"
    context_object_name: str | None = None
    slug_url_kwarg: str = "slug"
    pk_url_kwarg: str = "pk"
    kwargs: dict[str, Any]

    def __init_subclass__(cls) -> None:
        from flash_db.validator import ModelValidator

        model = getattr(cls, "model", None)
        base_classes = ("DetailView", "CreateView", "UpdateView", "DeleteView")

        if model is None and cls.__name__ not in base_classes:
            msg = (
                f"The '{cls.__name__}' is missing the required 'model' attribute. "
                f"Usage: class {cls.__name__}(DetailView): model = MyModelClass"
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

    async def get_object(
        self,
        queryset: QuerySet[T] | None = None,
        *,
        auto_error: bool = True,
    ) -> T | None:
        if self.db is None:
            msg = "Database session is required but not set."
            raise RuntimeError(msg)

        if queryset is None:
            queryset = self.get_queryset()

        pk = self.kwargs.get(self.pk_url_kwarg)
        slug = self.kwargs.get(self.slug_url_kwarg)

        if pk is not None:
            queryset = queryset.filter(self.model.id == pk)
        elif slug is not None:
            field = getattr(self.model, self.slug_field, None)
            if field is None:
                msg = f"Model {self.model.__name__} has no field '{self.slug_field}'"
                raise AttributeError(msg)
            queryset = queryset.filter(field == slug)
        else:
            msg = f"URL must include '{self.pk_url_kwarg}' or '{self.slug_url_kwarg}'"
            raise AttributeError(msg)

        try:
            obj = await queryset.first(self.db)
        except (AttributeError, TypeError):
            raise
        except OperationalError as e:
            logger.exception("Database connection error")
            raise HTTPException(
                status_code=503,
                detail="Database service temporarily unavailable.",
            ) from e
        except (IntegrityError, DatabaseError) as e:
            logger.exception("Database execution error")
            raise HTTPException(
                status_code=500,
                detail="Internal database error occurred.",
            ) from e
        except Exception as e:
            logger.exception("Unexpected system error")
            raise HTTPException(status_code=500, detail="Internal server error") from e

        if not obj and auto_error:
            raise HTTPException(
                status_code=404,
                detail=f"{self.model.__name__} not found.",
            )

        return cast("T", obj) if obj else None

    def _get_model_fields(self) -> list[str]:
        try:
            return [col.name for col in self.model.__table__.columns]
        except Exception:
            return ["<unable to fetch fields>"]
