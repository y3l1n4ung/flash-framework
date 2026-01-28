from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING, ClassVar

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

if TYPE_CHECKING:
    from .manager import ModelManager

try:
    from typing import Self
except ImportError:  # pragma: no cover
    from typing_extensions import Self


class Model(AsyncAttrs, DeclarativeBase):
    __abstract__ = True
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    objects: ClassVar[ModelManager[Self]]  # type: ignore[invalid-type-arguments]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        from .manager import ModelManager

        cls.objects = ModelManager(cls)


class TimestampMixin:
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
