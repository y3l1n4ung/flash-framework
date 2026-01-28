import logging
from typing import Any, Generic, TypeVar

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


class SingleObjectMixin(Generic[T]):
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
            raise TypeError(
                msg,
            )

        if model is not None:
            try:
                ModelValidator.validate_model(model)
            except TypeError as e:
                raise TypeError(str(e)) from e

        return super().__init_subclass__()

    def get_queryset(self) -> QuerySet[T]:
        """
        Return the QuerySet used to look up the object.

        Override this method to add filtering, select_related, or prefetch_related.

        Examples:
            >>> def get_queryset(self):
            ...     # Add related objects for efficiency
            ...     return self.model.objects.select_related("author")
        """
        if self.queryset is not None:
            return self.queryset
        return self.model.objects.all()

    async def get_object(
        self,
        queryset: QuerySet[T] | None = None,
        auto_error: bool = True,
    ) -> T | None:
        """
        Fetch a single object from the database.

        Args:
            queryset: Optional QuerySet override. Uses self.get_queryset() if None.
            auto_error: If True, raise HTTPException(404) when object not found.
                       If False, return None.

        Returns:
            T: The model instance, or None if not found and auto_error=False.

        Raises:
            RuntimeError: If self.db is not assigned.
            AttributeError: If neither pk nor slug in URL parameters.
            AttributeError: If slug_field doesn't exist on model.
            HTTPException(404): Object not found and auto_error=True.
            HTTPException(503): Database unavailable.
            HTTPException(500): Database integrity or unexpected error.

        Examples:
            >>> view = ProductDetail()
            >>> view.model = Product
            >>> view.db = session
            >>> view.kwargs = {"pk": 1}
            >>> product = await view.get_object()
        """
        if self.db is None:
            msg = (
                "Database session is required but not set. "
                "Ensure your view is using Depends(get_db) for 'db' parameter."
            )
            raise RuntimeError(
                msg,
            )

        if queryset is None:
            queryset = self.get_queryset()

        pk = self.kwargs.get(self.pk_url_kwarg)
        slug = self.kwargs.get(self.slug_url_kwarg)

        try:
            if pk is not None:
                logger.debug(
                    "Looking up %s by %s=%s",
                    self.model.__name__,
                    self.pk_url_kwarg,
                    pk,
                )
                queryset = queryset.filter(self.model.id == pk)

            elif slug is not None:
                field = getattr(self.model, self.slug_field, None)
                if field is None:
                    msg = (
                        f"Model {self.model.__name__} has no field "
                        f"'{self.slug_field}'. Valid fields: {self._get_model_fields()}"
                    )
                    raise AttributeError(
                        msg,
                    )

                logger.debug(
                    "Looking up %s by %s=%s",
                    self.model.__name__,
                    self.slug_field,
                    slug,
                )
                queryset = queryset.filter(field == slug)

            else:
                # Neither lookup parameter provided
                available_params = list(self.kwargs.keys())
                msg = (
                    f"URL must include '{self.pk_url_kwarg}' or "
                    f"'{self.slug_url_kwarg}' parameter. "
                    f"Available: {available_params}. "
                    f"Configure 'pk_url_kwarg' and 'slug_url_kwarg' to match your URL."
                )
                raise AttributeError(
                    msg,
                )

            obj = await queryset.first(self.db)

        except OperationalError as e:
            logger.exception(
                "Database connection error while fetching %s",
                self.model.__name__,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "Database service temporarily unavailable. Please try again later."
                ),
            ) from e

        except IntegrityError as e:
            logger.exception(
                "Database integrity error while fetching %s",
                self.model.__name__,
            )
            raise HTTPException(
                status_code=500,
                detail="Database integrity error. Please contact support.",
            ) from e

        except DatabaseError as e:
            logger.exception(
                "Database error while fetching %s: %s",
                self.model.__name__,
            )
            raise HTTPException(
                status_code=500,
                detail="Database error. Please try again later.",
            ) from e

        except (AttributeError, TypeError):
            logger.exception("Configuration error in %s", self.__class__.__name__)
            raise

        except Exception as e:
            logger.exception(
                "Unexpected error fetching %s: %s",
                self.model.__name__,
                type(e).__name__,
            )
            raise HTTPException(status_code=500, detail="Internal server error") from e

        if not obj and auto_error:
            logger.info(
                "%s not found with %s=%s",
                self.model.__name__,
                self.pk_url_kwarg or self.slug_url_kwarg,
                pk or slug,
            )
            raise HTTPException(
                status_code=404,
                detail=f"{self.model.__name__} not found.",
            )

        logger.debug("Successfully fetched %s", self.model.__name__)
        return obj

    def _get_model_fields(self) -> list[str]:
        """Return list of model field names for error messages."""
        try:
            return [col.name for col in self.model.__table__.columns]
        except Exception:
            return ["<unable to fetch fields>"]
