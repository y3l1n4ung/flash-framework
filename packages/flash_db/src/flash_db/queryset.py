from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Sequence, Type, TypeVar

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from .models import Model

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ColumnElement, Select

T = TypeVar("T", bound=Model)


class QuerySet(Generic[T]):
    """
    Represents a lazy database query for a specific model type.

    A QuerySet stores a SQLAlchemy `Select` statement and allows query
    conditions to be composed without executing the query immediately.
    """

    def __init__(self, model: Type[T], stmt: Select[tuple[T]]):
        self.model: Type[T] = model
        self._stmt: Select[tuple[T]] = stmt

    def filter(self, *conditions: ColumnElement[bool]) -> QuerySet[T]:
        """
        Add WHERE criteria to the query.
        """
        if not conditions:
            return self
        return QuerySet(self.model, self._stmt.where(*conditions))

    def order_by(self, *criterion: Any) -> QuerySet[T]:
        """
        Add ORDER BY criteria to the query.
        """
        return QuerySet(self.model, self._stmt.order_by(*criterion))

    def limit(self, count: int) -> QuerySet[T]:
        """
        Limit the number of records returned.
        """
        return QuerySet(self.model, self._stmt.limit(count))

    def offset(self, count: int) -> QuerySet[T]:
        """
        Apply an offset to the result set.
        """
        return QuerySet(self.model, self._stmt.offset(count))

    def load_related(self, *fields: str) -> QuerySet[T]:
        """
        Eagerly load related relationships to prevent N+1 queries.
        """
        stmt = self._stmt
        for field in fields:
            stmt = stmt.options(joinedload(getattr(self.model, field)))
        return QuerySet(self.model, stmt)

    async def fetch(self, db: AsyncSession) -> Sequence[T]:
        """
        Execute the query and return all matching records.
        """
        result = await db.scalars(self._stmt)
        return result.unique().all()

    async def first(self, db: AsyncSession) -> T | None:
        """
        Execute the query and return the first matching record or None.
        """
        result = await db.scalars(self._stmt.limit(1))
        return result.one_or_none()

    async def count(self, db: AsyncSession) -> int:
        """
        Return the total number of records matching the query.
        """
        count_stmt = select(func.count()).select_from(self._stmt.subquery())
        return await db.scalar(count_stmt) or 0

    async def exists(self, db: AsyncSession) -> bool:
        """
        Check if any records exist matching the query.
        """
        return await self.count(db) > 0

    async def update(self, db: AsyncSession, **values: Any) -> int:
        """
        Perform a bulk update on all records matched by the query.
        """
        where_clause = self._stmt._where_criteria
        if not where_clause:
            msg = "Refusing to update without filters"
            raise ValueError(msg)

        stmt = update(self.model).where(*where_clause).values(**values)
        try:
            result = await db.execute(stmt)
            await db.commit()
            return getattr(result, "rowcount", 0)
        except SQLAlchemyError as e:
            await db.rollback()
            msg = f"Database error during bulk update: {e}"
            raise RuntimeError(msg) from e

    async def delete(self, db: AsyncSession) -> int:
        """
        Delete all records matched by the query.
        """
        where_clause = self._stmt._where_criteria
        if not where_clause:
            msg = "Refusing to delete without filters"
            raise ValueError(msg)

        stmt = delete(self.model).where(*where_clause)
        try:
            result = await db.execute(stmt)
            await db.commit()
            return getattr(result, "rowcount", 0)
        except SQLAlchemyError as e:
            await db.rollback()
            msg = f"Database error during bulk delete: {e}"
            raise RuntimeError(msg) from e
