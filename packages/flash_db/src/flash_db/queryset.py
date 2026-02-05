from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Sequence, Type, TypeVar

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from .models import Model

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ColumnElement, Select

    from .expressions import Q

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

    def filter(
        self, *conditions: Q | ColumnElement[bool], **kwargs: object
    ) -> QuerySet[T]:
        """
        Add WHERE criteria to the query.

        Args:
            *conditions: Positional SQLAlchemy expressions or Q objects.
            **kwargs: Keyword arguments for basic equality checks.

        Returns:
            A new QuerySet instance with the conditions applied.

        Example:
            >>> articles = await Article.objects.filter(
            ...     title="Intro", id__gt=10
            ... ).fetch(db)
            >>> articles = await Article.objects.filter(
            ...     Q(title="A") | Q(title="B")
            ... ).fetch(db)
        """
        if not conditions and not kwargs:
            return self

        stmt = self._stmt
        from .expressions import Q

        # Handle positional arguments (expressions or Q objects)
        for cond in conditions:
            if isinstance(cond, Q):
                resolved = cond.resolve(self.model)
                if resolved is not None:
                    stmt = stmt.where(resolved)
            else:
                stmt = stmt.where(cond)

        # Handle keyword arguments
        for key, value in kwargs.items():
            stmt = stmt.where(getattr(self.model, key) == value)

        return QuerySet(self.model, stmt)

    def exclude(
        self, *conditions: Q | ColumnElement[bool], **kwargs: object
    ) -> QuerySet[T]:
        """
        Add NOT WHERE criteria to the query.

        Args:
            *conditions: Positional SQLAlchemy expressions or Q objects.
            **kwargs: Keyword arguments for basic inequality checks.

        Returns:
            A new QuerySet instance with the negation applied.

        Example:
            >>> articles = await Article.objects.exclude(title="Outdated").fetch(db)
        """
        if not conditions and not kwargs:
            return self

        from sqlalchemy import not_

        from .expressions import Q

        stmt = self._stmt

        # Handle positional arguments
        for cond in conditions:
            if isinstance(cond, Q):
                resolved = cond.resolve(self.model)
                if resolved is not None:
                    stmt = stmt.where(not_(resolved))
            else:
                stmt = stmt.where(not_(cond))

        # Handle keyword arguments
        for key, value in kwargs.items():
            stmt = stmt.where(getattr(self.model, key) != value)

        return QuerySet(self.model, stmt)

    def distinct(self, *criterion: Any) -> QuerySet[T]:
        """
        Add DISTINCT criteria to the query.
        """
        return QuerySet(self.model, self._stmt.distinct(*criterion))

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

    def only(self, *fields: str) -> QuerySet[T]:
        """
        Load only the specified fields.
        """
        from sqlalchemy.orm import load_only

        cols = [getattr(self.model, f) for f in fields]
        return QuerySet(self.model, self._stmt.options(load_only(*cols)))

    def defer(self, *fields: str) -> QuerySet[T]:
        """
        Defer loading of the specified fields.
        """
        from sqlalchemy.orm import defer

        stmt = self._stmt
        for field in fields:
            stmt = stmt.options(defer(getattr(self.model, field)))
        return QuerySet(self.model, stmt)

    def select_related(self, *fields: str) -> QuerySet[T]:
        """
        Eagerly load related relationships to prevent N+1 queries.
        """
        stmt = self._stmt
        for field in fields:
            stmt = stmt.options(joinedload(getattr(self.model, field)))
        return QuerySet(self.model, stmt)

    def prefetch_related(self, *fields: str) -> QuerySet[T]:
        """
        Eagerly load related relationships using separate queries (SELECT IN).
        """
        stmt = self._stmt
        for field in fields:
            stmt = stmt.options(selectinload(getattr(self.model, field)))
        return QuerySet(self.model, stmt)

    async def fetch(self, db: AsyncSession) -> Sequence[T]:
        """
        Execute the query and return all matching records.
        """
        result = await db.scalars(self._stmt)
        return result.unique().all()

    async def values(self, db: AsyncSession, *fields: str) -> list[dict[str, Any]]:
        """
        Return a list of dictionaries for the specified fields.

        Args:
            db: The database session.
            *fields: Names of the fields to include in the dictionary.
                If none specified, all model columns are included.

        Returns:
            A list of mappings (dictionaries).

        Example:
            >>> data = await Article.objects.values(db, "title", "content")
            >>> # [{'title': 'A', 'content': '...'}, ...]
        """
        if not fields:
            # Select all columns if no fields specified
            stmt = select(*self.model.__table__.columns)
        else:
            cols = [getattr(self.model, f) for f in fields]
            stmt = select(*cols).select_from(self.model)

        if self._stmt._where_criteria:
            stmt = stmt.where(*self._stmt._where_criteria)
        if self._stmt._order_by_clauses:
            stmt = stmt.order_by(*self._stmt._order_by_clauses)
        if self._stmt._limit_clause is not None:
            stmt = stmt.limit(self._stmt._limit_clause)
        if self._stmt._offset_clause is not None:
            stmt = stmt.offset(self._stmt._offset_clause)

        result = await db.execute(stmt)
        return [dict(row._mapping) for row in result]

    async def values_list(
        self, db: AsyncSession, *fields: str, flat: bool = False
    ) -> list[Any]:
        """
        Return a list of tuples for the specified fields.
        If flat=True and only one field is specified, return a flat list.
        """
        if not fields:
            # Select all columns if no fields specified
            stmt = select(*self.model.__table__.columns)
        else:
            cols = [getattr(self.model, f) for f in fields]
            stmt = select(*cols).select_from(self.model)

        if self._stmt._where_criteria:
            stmt = stmt.where(*self._stmt._where_criteria)
        if self._stmt._order_by_clauses:
            stmt = stmt.order_by(*self._stmt._order_by_clauses)
        if self._stmt._limit_clause is not None:
            stmt = stmt.limit(self._stmt._limit_clause)
        if self._stmt._offset_clause is not None:
            stmt = stmt.offset(self._stmt._offset_clause)

        result = await db.execute(stmt)
        if flat:
            if len(fields) != 1:
                msg = "flat=True can only be used with a single field"
                raise ValueError(msg)
            return list(result.scalars().all())

        return [tuple(row) for row in result]

    async def first(self, db: AsyncSession) -> T | None:
        """
        Execute the query and return the first matching record or None.
        """
        result = await db.scalars(self._stmt.limit(1))
        return result.unique().one_or_none()

    async def latest(self, db: AsyncSession, field: str = "created_at") -> T | None:
        """
        Return the latest object in the table based on the given field.
        """
        return await self.order_by(getattr(self.model, field).desc()).first(db)

    async def earliest(self, db: AsyncSession, field: str = "created_at") -> T | None:
        """
        Return the earliest object in the table based on the given field.
        """
        return await self.order_by(getattr(self.model, field).asc()).first(db)

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
