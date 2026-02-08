from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Mapping,
    Type,
    TypeVar,
)

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement, Select

    from flash_db.models import Model

T = TypeVar("T", bound="Model")


class QuerySetBase(Generic[T]):
    """
    Fundamental state and identity for a QuerySet.

    This base class manages the core attributes shared across all QuerySet layers:
    the target model, the SQLAlchemy Select statement, and calculated field
    annotations.
    """

    def __init__(
        self,
        model: Type[T],
        stmt: Select,
        _annotations: Mapping[str, ColumnElement[Any]] | None = None,
    ):
        self.model: Type[T] = model
        self._stmt: Select = stmt
        self._annotations: Mapping[str, ColumnElement[Any]] = _annotations or {}

    def _clone(self, stmt: Select | None = None) -> Any:
        """
        Return a new instance of the current class with updated statement.

        Using self.__class__ ensures that the top-most class in the
        inheritance chain is instantiated, preserving all capabilities (construction,
        execution, etc.) in the resulting object.
        """
        return self.__class__(
            self.model,
            stmt if stmt is not None else self._stmt,
            _annotations=dict(self._annotations),
        )
