from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, Sequence, Type, TypeVar

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import joinedload, selectinload

from .expressions import Resolvable
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
    Queries are executed only when calling an execution method like `fetch()`,
    `first()`, or `count()`.

    Examples:
        >>> qs = Article.objects.filter(title="Hello")

        >>> qs = (Article.objects.filter(id__gt=10)
        ...       .exclude(status="draft").order_by("-id"))
    """

    def __init__(self, model: Type[T], stmt: Select):
        self.model: Type[T] = model
        self._stmt: Select = stmt

    def _clone(self, stmt: Select | None = None) -> QuerySet[T]:
        """
        Return a new QuerySet instance with the same model and result type.
        """
        return QuerySet(self.model, stmt if stmt is not None else self._stmt)

    def filter(
        self, *conditions: ColumnElement[bool] | Resolvable, **kwargs: object
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
            # SELECT * FROM articles WHERE title = 'Intro' AND id > 10;
            >>> articles = await Article.objects.filter(
            ...     Q(title="A") | Q(title="B")
            ... ).fetch(db)
            # SELECT * FROM articles WHERE title = 'A' OR title = 'B';
        """
        if not conditions and not kwargs:
            return self

        stmt = self._stmt

        # Handle positional arguments (raw SQLAlchemy expressions or Q objects)
        for cond in conditions:
            if isinstance(cond, Resolvable):
                resolved = cond.resolve(self.model)
                if resolved is not None:
                    stmt = stmt.where(resolved)
            else:
                stmt = stmt.where(cond)

        # Handle keyword arguments (simple equality)
        for key, value in kwargs.items():
            if hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) == value)

        return self._clone(stmt)

    def exclude(
        self, *conditions: ColumnElement[bool] | Resolvable, **kwargs: object
    ) -> QuerySet[T]:
        """
        Add NOT WHERE criteria to the query.

        Arguments work exactly like `filter()`, but the conditions are negated.

        Returns:
            A new QuerySet instance with the negation applied.

        Example:
            >>> articles = await Article.objects.exclude(title="Outdated").fetch(db)
            # SELECT * FROM articles WHERE title != 'Outdated';
        """
        if not conditions and not kwargs:
            return self

        from sqlalchemy import not_

        stmt = self._stmt

        # Handle positional arguments
        for cond in conditions:
            if isinstance(cond, Resolvable):
                resolved = cond.resolve(self.model)
                if resolved is not None:
                    stmt = stmt.where(not_(resolved))
            else:
                stmt = stmt.where(not_(cond))

        # Handle keyword arguments
        for key, value in kwargs.items():
            if hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) != value)

        return self._clone(stmt)

    def distinct(self, *criterion: Any) -> QuerySet[T]:
        """
        Add DISTINCT criteria to the query.

        Example:
            >>> articles = await Article.objects.distinct().fetch(db)
            # SELECT DISTINCT * FROM articles;
        """
        return self._clone(self._stmt.distinct(*criterion))

    def order_by(self, *criterion: Any) -> QuerySet[T]:
        """
        Add ORDER BY criteria to the query.

        Example:
            >>> Article.objects.order_by("title")
            # SELECT * FROM articles ORDER BY title ASC;

            >>> Article.objects.order_by(Article.id.desc())
            # SELECT * FROM articles ORDER BY id DESC;
        """
        return self._clone(self._stmt.order_by(*criterion))

    def limit(self, count: int) -> QuerySet[T]:
        """
        Limit the number of records returned.

        Example:
            >>> articles = await Article.objects.limit(10).fetch(db)
            # SELECT * FROM articles LIMIT 10;
        """
        return self._clone(self._stmt.limit(count))

    def offset(self, count: int) -> QuerySet[T]:
        """
        Apply an offset to the result set.

        Example:
            >>> articles = await Article.objects.offset(10).fetch(db)
            # SELECT * FROM articles OFFSET 10;
        """
        return self._clone(self._stmt.offset(count))

    def only(self, *fields: str) -> QuerySet[T]:
        """
        Load only the specified fields.

        Example:
            >>> Article.objects.only("title", "id")
            # SELECT id, title FROM articles;
        """
        from sqlalchemy.orm import load_only

        cols = [getattr(self.model, f) for f in fields]
        return self._clone(self._stmt.options(load_only(*cols)))

    def defer(self, *fields: str) -> QuerySet[T]:
        """
        Defer loading of the specified fields.

        Example:
            >>> articles = await Article.objects.defer("content").fetch(db)
            # SELECT id, title, ... FROM articles; (content column excluded)
        """
        from sqlalchemy.orm import defer

        stmt = self._stmt
        for field in fields:
            stmt = stmt.options(defer(getattr(self.model, field)))
        return self._clone(stmt)

    def select_related(self, *fields: str) -> QuerySet[T]:
        """
        Eagerly load related relationships using SQL JOINs.
        Best for 1-to-1 or Many-to-1 relationships.

        !!! warning
            Using `select_related` for one-to-many relationships (collections) can lead
            to row duplication and decreased performance. Use `prefetch_related` instead
            for these cases.

        Example:
            >>> articles = await Article.objects.select_related("author").fetch(db)
            # SELECT * FROM articles JOIN authors ON articles.author_id = authors.id;
        """
        stmt = self._stmt
        for field in fields:
            stmt = stmt.options(joinedload(getattr(self.model, field)))
        return self._clone(stmt)

    def prefetch_related(self, *fields: str) -> QuerySet[T]:
        """
        Eagerly load related relationships using separate queries.
        Best for Many-to-Many or 1-to-Many relationships.

        Example:
            >>> articles = await Article.objects.prefetch_related("tags").fetch(db)
            # SELECT * FROM articles;
            # SELECT * FROM tags WHERE id IN (...);
        """
        stmt = self._stmt
        for field in fields:
            stmt = stmt.options(selectinload(getattr(self.model, field)))
        return self._clone(stmt)

    async def fetch(self, db: AsyncSession) -> Sequence[T]:
        """
        Execute the query and return all matching records.

        Example:
            >>> articles = await Article.objects.all().fetch(db)
            # SELECT * FROM articles;
        """
        result = await db.execute(self._stmt)
        return result.scalars().unique().all()

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
            >>> data = await Article.objects.filter(id=1).values("title", "id")
            # [{'id': 1, 'title': 'Hello'}]
        """
        if not fields:
            stmt = select(*self.model.__table__.columns)
        else:
            cols = [getattr(self.model, f) for f in fields]
            stmt = select(*cols).select_from(self.model)

            # SELECT * FROM articles ORDER BY created_at ASC LIMIT 1;
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

        Example:
            >>> titles = await Article.objects.values_list(db, "title", flat=True)
            # ['Hello', 'World']
        """
        if not fields:
            stmt = select(*self.model.__table__.columns)
        else:
            cols = [getattr(self.model, f) for f in fields]
            stmt = select(*cols).select_from(self.model)

            # SELECT * FROM articles ORDER BY created_at ASC LIMIT 1;
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

        Example:
            >>> article = await Article.objects.first(db)
            # SELECT * FROM articles LIMIT 1;
        """
        stmt = self._stmt.limit(1)
        result = await db.scalars(stmt)
        return result.unique().one_or_none()

    async def last(self, db: AsyncSession) -> T | None:
        """
        Return the last record by primary key descending.

        !!! note
            This method appends the primary key descending order to
            any existing ordering.

        Example:
            >>> await Article.objects.last(db)
            # SELECT * FROM articles ORDER BY id DESC LIMIT 1;
        """
        return await self.order_by(self.model.id.desc()).first(db)

    async def latest(self, db: AsyncSession, field: str = "created_at") -> T | None:
        """
        Return the latest object in the table based on the given field.

        !!! note
            This method appends the specified field's descending order to
            any existing ordering.

        Example:
            >>> article = await Article.objects.latest(db)
            # SELECT * FROM articles ORDER BY created_at DESC LIMIT 1;
        """
        return await self.order_by(getattr(self.model, field).desc()).first(db)

    async def earliest(self, db: AsyncSession, field: str = "created_at") -> T | None:
        """
        Return the earliest object in the table based on the given field.

        !!! note
            This method appends the specified field's ascending order to
            any existing ordering.

        Example:
            >>> article = await Article.objects.earliest(db)
        """
        return await self.order_by(getattr(self.model, field).asc()).first(db)

    async def count(self, db: AsyncSession) -> int:
        """
        Return the total number of records matching the query.

        Example:
            >>> count = await Article.objects.count(db)
            # SELECT count(*) FROM articles;
        """
        count_stmt = select(func.count()).select_from(self._stmt.subquery())
        return await db.scalar(count_stmt) or 0

    async def exists(self, db: AsyncSession) -> bool:
        """
        Check if any records exist matching the query.
        """
        return await self.count(db) > 0

    async def update(
        self, db: AsyncSession, **values: ColumnElement[Any] | Resolvable | object
    ) -> int:
        """
        Perform a bulk update on all records matched by the query.

        Example:
            >>> count = await Article.objects.filter(
            ...     title="Old"
            ... ).update(db, title="New")
            # UPDATE articles SET title = 'New' WHERE title = 'Old';
        """
        where_clause = self._stmt._where_criteria
        if not where_clause:
            msg = "Refusing to update without filters"
            raise ValueError(msg)

        # Resolve any F expressions or other resolvables in the values
        resolved_values = {
            k: v.resolve(self.model) if isinstance(v, Resolvable) else v
            for k, v in values.items()
        }

        stmt = update(self.model).where(*where_clause).values(resolved_values)
        result = await db.execute(stmt)
        return getattr(result, "rowcount", 0)

    async def delete(self, db: AsyncSession) -> int:
        """
        Delete all records matched by the query.

        Example:
            >>> count = await Article.objects.filter(title="Trash").delete(db)
            # DELETE FROM articles WHERE title = 'Trash';
        """
        where_clause = self._stmt._where_criteria
        if not where_clause:
            msg = "Refusing to delete without filters"
            raise ValueError(msg)

        stmt = delete(self.model).where(*where_clause)
        result = await db.execute(stmt)
        return getattr(result, "rowcount", 0)
