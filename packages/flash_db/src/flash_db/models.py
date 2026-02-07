from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .exceptions import DoesNotExistError, MultipleObjectsReturnedError

if TYPE_CHECKING:
    from .manager import ModelManager

try:
    from typing import Self
except ImportError:  # pragma: no cover
    from typing_extensions import Self


class Model(AsyncAttrs, DeclarativeBase):
    """
    Base class for all database models.
    Provides an automatic `objects` manager and an `id` primary key.

    Example:
        >>> class User(Model):
        ...     __tablename__ = "users"
        ...     name: Mapped[str] = mapped_column()
    """

    __abstract__ = True
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    objects: ClassVar[ModelManager[Self]]  # type: ignore[invalid-type-arguments]

    # Model-specific exception aliases
    DoesNotExist = DoesNotExistError
    MultipleObjectsReturned = MultipleObjectsReturnedError

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__(**kwargs)
        from .manager import ModelManager

        if not cls.__dict__.get("__abstract__"):
            cls.objects = ModelManager(cls)


class TimestampMixin:
    """
    Mixin that adds `created_at` and `updated_at` fields to a model.

    Example:
        >>> class Post(Model, TimestampMixin):
        ...     __tablename__ = "posts"
        ...     title: Mapped[str] = mapped_column()
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_onupdate=func.now(),
        nullable=True,
    )


class SoftDeleteMixin:
    """
    Mixin that adds a `deleted_at` field for logical record deletion.

    Example:
        >>> class Note(Model, SoftDeleteMixin):
        ...     __tablename__ = "notes"
        ...     text: Mapped[str] = mapped_column()
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
