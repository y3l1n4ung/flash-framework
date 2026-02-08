from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Mapping,
    Self,
    Type,
    TypeVar,
)

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement, Select

    from flash_db.models import Model

T = TypeVar("T", bound="Model")


class QuerySetBase(Generic[T]):
    """
    Base class that holds the core state of a query.

    It stores the model, the SQLAlchemy Select statement, and any calculated
    fields (annotations). Every change to the query creates a new copy
    to keep the original safe and unchanged.
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

    def _clone(self, stmt: Select | None = None) -> Self:
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

    @property
    def _where_criteria(self) -> Any:
        """Helper to access statement where criteria safely."""
        return self._stmt._where_criteria

    @property
    def _having_criteria(self) -> Any:
        """Helper to access statement having criteria safely."""
        return self._stmt._having_criteria

    @property
    def _group_by_clauses(self) -> Any:
        """Helper to access statement group by clauses safely."""
        return self._stmt._group_by_clauses

    @property
    def _order_by_clauses(self) -> Any:
        """Helper to access statement order by clauses safely."""
        return self._stmt._order_by_clauses

    @property
    def _limit_clause(self) -> Any:
        """Helper to access statement limit clause safely."""
        return self._stmt._limit_clause

    @property
    def _offset_clause(self) -> Any:
        """Helper to access statement offset clause safely."""
        return self._stmt._offset_clause

    @property
    def _distinct(self) -> Any:
        """Helper to access statement distinct attribute safely."""
        return self._stmt._distinct
