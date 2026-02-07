from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Mapping,
    Sequence,
    Type,
    TypeVar,
    cast,
)

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

    def __init__(
        self,
        model: Type[T],
        stmt: Select,
        _annotations: Mapping[str, ColumnElement[Any]] | None = None,
    ):
        self.model: Type[T] = model
        self._stmt: Select = stmt
        self._annotations: Mapping[str, ColumnElement[Any]] = _annotations or {}

    def _clone(self, stmt: Select | None = None) -> QuerySet[T]:
        """Return a new QuerySet instance with the same model and result type."""
        # Each modification returns a new instance to ensure immutability.
        return QuerySet(
            self.model,
            stmt if stmt is not None else self._stmt,
            _annotations=dict(self._annotations),
        )

    # --- Chainable methods (Simple) ---

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

        # Reduce bandwidth by selecting only required columns.
        cols = [getattr(self.model, f) for f in fields]
        return self._clone(self._stmt.options(load_only(*cols)))

    def defer(self, *fields: str) -> QuerySet[T]:
        """
        Defer loading of the specified fields.

        Example:
            >>> articles = await Article.objects.defer("content").fetch(db)
            # SELECT id, title, ... FROM articles; (content excluded)
        """
        from sqlalchemy.orm import defer

        stmt = self._stmt
        for field in fields:
            # Exclude large columns from the initial load to speed up query.
            stmt = stmt.options(defer(getattr(self.model, field)))
        return self._clone(stmt)

    def select_related(self, *fields: str) -> QuerySet[T]:
        """
        Eagerly load related relationships using SQL JOINs.
        Best for 1-to-1 or Many-to-1 relationships.

        Example:
            >>> articles = await Article.objects.select_related("author").fetch(db)
            # SELECT articles.*, authors.* FROM articles
            # JOIN authors ON articles.author_id = authors.id;
        """
        stmt = self._stmt
        for field in fields:
            # Use JOIN to fetch related data in a single round-trip.
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
            # Load relationships where JOINs would cause excessive row multiplication.
            stmt = stmt.options(selectinload(getattr(self.model, field)))
        return self._clone(stmt)

    async def fetch(self, db: AsyncSession) -> Sequence[T]:
        """
        Execute query and return results as model instances.
        Maps annotations back to instances if present.

        Example:
            >>> articles = await Article.objects.all().fetch(db)
            # SELECT * FROM articles;
        """
        result = await db.execute(self._stmt)

        # Return scalars directly when no calculated fields are present.
        if not self._annotations:
            return result.scalars().unique().all()

        # Handle rows unique by Model instance to prevent duplicates from joins.
        rows = result.unique().all()
        objects: list[T] = []
        for row in rows:
            instance = cast("T", row[0])
            for i, key in enumerate(self._annotations.keys(), start=1):
                # Attach calculated SQL values to the model instance.
                setattr(instance, key, row[i])
            objects.append(instance)
        return objects

    async def first(self, db: AsyncSession) -> T | None:
        """
        Execute query and return the first result or None.

        Example:
            >>> article = await Article.objects.first(db)
            # SELECT * FROM articles LIMIT 1;
        """
        stmt = self._stmt.limit(1)
        result = await db.execute(stmt)

        if not self._annotations:
            return result.scalars().unique().one_or_none()

        row = result.unique().one_or_none()
        if not row:
            return None

        instance = cast("T", row[0])
        for i, key in enumerate(self._annotations.keys(), start=1):
            setattr(instance, key, row[i])
        return instance

    async def last(self, db: AsyncSession) -> T | None:
        """
        Return the last record by primary key descending.

        Example:
            >>> await Article.objects.last(db)
            # SELECT * FROM articles ORDER BY id DESC LIMIT 1;
        """
        return await self.order_by(self.model.id.desc()).first(db)

    async def latest(self, db: AsyncSession, field: str = "created_at") -> T | None:
        """
        Return the latest object in the table based on the given field.

        Example:
            >>> article = await Article.objects.latest(db)
            # SELECT * FROM articles ORDER BY created_at DESC LIMIT 1;
        """
        return await self.order_by(getattr(self.model, field).desc()).first(db)

    async def earliest(self, db: AsyncSession, field: str = "created_at") -> T | None:
        """
        Return the earliest object in the table based on the given field.

        Example:
            >>> article = await Article.objects.earliest(db)
            # SELECT * FROM articles ORDER BY created_at ASC LIMIT 1;
        """
        return await self.order_by(getattr(self.model, field).asc()).first(db)

    async def values(self, db: AsyncSession, *fields: str) -> list[dict[str, Any]]:
        """
        Return results as a list of dictionaries.

        Example:
            >>> data = await Article.objects.filter(id=1).values("title", "id")
            # SELECT title, id FROM articles WHERE id = 1;
            # [{'id': 1, 'title': 'Hello'}]
        """
        if not fields:
            stmt = select(*self.model.__table__.columns)
        else:
            cols: list[ColumnElement[Any]] = []
            for f in fields:
                # Retrieve either a model column or a defined annotation.
                if f in self._annotations:
                    cols.append(self._annotations[f])
                else:
                    cols.append(getattr(self.model, f))
            stmt = select(*cols).select_from(self.model)

        # Apply all filters and limits to the new statement.
        if self._stmt._where_criteria:
            stmt = stmt.where(*self._stmt._where_criteria)
        if self._stmt._having_criteria:
            stmt = stmt.having(*self._stmt._having_criteria)
        if self._stmt._group_by_clauses:
            stmt = stmt.group_by(*self._stmt._group_by_clauses)
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
        Return results as a list of tuples or flat values.

        Example:
            >>> titles = await Article.objects.values_list(db, "title", flat=True)
            # SELECT title FROM articles;
            # ['Hello', 'World']
        """
        if not fields:
            stmt = select(*self.model.__table__.columns)
        else:
            cols: list[ColumnElement[Any]] = []
            for f in fields:
                if f in self._annotations:
                    cols.append(self._annotations[f])
                else:
                    cols.append(getattr(self.model, f))
            stmt = select(*cols).select_from(self.model)

        # Apply existing criteria to ensure filtered results.
        if self._stmt._where_criteria:
            stmt = stmt.where(*self._stmt._where_criteria)
        if self._stmt._having_criteria:
            stmt = stmt.having(*self._stmt._having_criteria)
        if self._stmt._group_by_clauses:
            stmt = stmt.group_by(*self._stmt._group_by_clauses)
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

    async def count(self, db: AsyncSession) -> int:
        """
        Return total record count for the QuerySet.

        Example:
            >>> count = await Article.objects.count(db)
            # SELECT count(*) FROM (SELECT * FROM articles) AS subquery;
        """
        # Wrapped in a subquery to support DISTINCT and GROUP BY accurately.
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
        Execute bulk update on the QuerySet.

        Example:
            >>> await Article.objects.filter(id=1).update(db, title="New")
            # UPDATE articles SET title = 'New' WHERE id = 1;
        """
        where_clause = self._stmt._where_criteria
        # Prevent accidental full-table updates.
        if not where_clause:
            msg = "Refusing to update without filters"
            raise ValueError(msg)

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
            >>> await Article.objects.filter(title="Trash").delete(db)
            # DELETE FROM articles WHERE title = 'Trash';
        """
        where_clause = self._stmt._where_criteria
        # Prevent accidental full-table deletions.
        if not where_clause:
            msg = "Refusing to delete without filters"
            raise ValueError(msg)

        stmt = delete(self.model).where(*where_clause)
        result = await db.execute(stmt)
        return getattr(result, "rowcount", 0)

    def filter(
        self, *conditions: ColumnElement[bool] | Resolvable, **kwargs: object
    ) -> QuerySet[T]:
        """
        Add WHERE or HAVING criteria to the query.

        Example:
            >>> Product.objects.filter(name="A", price__gt=10)
            # SELECT * FROM products WHERE name = 'A' AND price > 10;

            >>> Product.objects.filter(Q(price__lt=5) | Q(stock=0))
            # SELECT * FROM products WHERE price < 5 OR stock = 0;

            >>> Product.objects.annotate(n=Count('revs')).filter(n__gt=5, status='a')
            # SELECT products.*, count(revs.id) AS n FROM products
            # LEFT JOIN revs ON ... GROUP BY products.id
            # HAVING count(revs.id) > 5 AND status = 'a';
        """
        if not conditions and not kwargs:
            return self

        stmt = self._stmt

        # Handle positional conditions like Q objects or raw expressions.
        for cond in conditions:
            expr, is_agg = self._resolve_condition(cond)
            if expr is not None:
                # Route aggregates to HAVING and regular fields to WHERE.
                stmt = self._attach_condition(stmt, expr, is_agg=is_agg)

        # Handle Django-style keyword lookups.
        for key, value in kwargs.items():
            expr, is_agg = self._resolve_lookup(key, value)
            if expr is not None:
                stmt = self._attach_condition(stmt, expr, is_agg=is_agg)

        return self._clone(stmt)

    def exclude(
        self, *conditions: ColumnElement[bool] | Resolvable, **kwargs: object
    ) -> QuerySet[T]:
        """
        Add negative WHERE or HAVING criteria to the query.

        Example:
            >>> Product.objects.exclude(price__gt=100)
            # SELECT * FROM products WHERE NOT (price > 100);

            >>> Product.objects.annotate(n=Count('revs')).exclude(n__lt=1)
            # SELECT ..., count(revs.id) AS n ... HAVING NOT (count(id) < 1);
        """
        if not conditions and not kwargs:
            return self

        from sqlalchemy import not_

        stmt = self._stmt

        # Negate resolved conditions for exclusion logic.
        for cond in conditions:
            expr, is_agg = self._resolve_condition(cond)
            if expr is not None:
                stmt = self._attach_condition(stmt, not_(expr), is_agg=is_agg)

        # Similarly negate keyword lookups and route accordingly.
        for key, value in kwargs.items():
            expr, is_agg = self._resolve_lookup(key, value)
            if expr is not None:
                stmt = self._attach_condition(stmt, not_(expr), is_agg=is_agg)

        return self._clone(stmt)

    def annotate(self, **kwargs: ColumnElement[Any] | Resolvable) -> QuerySet[T]:
        """
        Add calculated fields to each row in the QuerySet.

        Example:
            >>> Article.objects.annotate(num_comments=Count("comments"))
            # SELECT articles.*, count(comments.id) AS num_comments
            # FROM articles LEFT JOIN comments ON ...
            # GROUP BY articles.id;

            >>> Article.objects.annotate(total_score=Sum("votes__value"))
            # SELECT articles.*, sum(votes.value) AS total_score
            # FROM articles LEFT JOIN votes ON ...
            # GROUP BY articles.id;
        """
        if not kwargs:
            return self

        from .expressions import Aggregate

        stmt = self._stmt
        new_annotations = dict(self._annotations)

        for key, expr in kwargs.items():
            if isinstance(expr, Resolvable):
                # Resolve Flash Aggregate/F classes into SA functions.
                resolved = expr.resolve(self.model, _annotations=new_annotations)
                if resolved is not None:
                    label = resolved.label(key)
                    stmt = stmt.add_columns(label)
                    new_annotations[key] = label

                # relationship aggregates automatically trigger OUTER JOINs.
                if isinstance(expr, Aggregate):
                    for join_attr in expr.get_joins(self.model):
                        stmt = stmt.outerjoin(join_attr)
            else:
                # Support raw SQLAlchemy expressions.
                label = cast("ColumnElement[Any]", expr).label(key)
                stmt = stmt.add_columns(label)
                new_annotations[key] = label

        # Requires grouping by primary key to calculate values per row.
        stmt = stmt.group_by(*self.model.__table__.primary_key)

        return QuerySet(self.model, stmt, _annotations=new_annotations)

    async def aggregate(
        self, db: AsyncSession, **kwargs: ColumnElement[Any] | Resolvable
    ) -> dict[str, Any]:
        """
        Return summary values for the entire QuerySet.

        Example:
            >>> await Article.objects.aggregate(db, total=Sum("views"))
            # SELECT sum(views) AS total FROM articles;

            >>> await Article.objects.filter(status='p').aggregate(db, c=Count('id'))
            # SELECT count(id) AS c FROM articles WHERE status = 'p';
        """
        if not kwargs:
            return {}

        agg_cols: list[ColumnElement[Any]] = []
        for key, expr in kwargs.items():
            if isinstance(expr, Resolvable):
                resolved = expr.resolve(self.model, _annotations=self._annotations)
                if resolved is not None:
                    agg_cols.append(resolved.label(key))
            else:
                agg_cols.append(cast("ColumnElement[Any]", expr).label(key))

        # Collapse results into a single summary row.
        stmt = select(*agg_cols).select_from(self.model)

        # Preserve original WHERE and HAVING filters.
        if self._stmt._where_criteria:
            stmt = stmt.where(*self._stmt._where_criteria)
        if self._stmt._having_criteria:
            stmt = stmt.having(*self._stmt._having_criteria)

        from .expressions import Aggregate

        # Join relationship tables if required for summary aggregates.
        for expr in kwargs.values():
            if isinstance(expr, Aggregate):
                for join_attr in expr.get_joins(self.model):
                    stmt = stmt.outerjoin(join_attr)

        result = await db.execute(stmt)
        mapping = result.mappings().first()
        return dict(mapping) if mapping else dict.fromkeys(kwargs, None)

    def _resolve_condition(
        self, cond: ColumnElement[bool] | Resolvable
    ) -> tuple[ColumnElement[bool] | None, bool]:
        """Resolve a positional condition and detect if it involves an aggregate."""
        if isinstance(cond, Resolvable):
            expr = cond.resolve(self.model, _annotations=self._annotations)
            if expr is None:
                return None, False
            # Determine if the expression tree contains aggregate functions.
            is_agg = self._contains_aggregate(cond) or self._contains_aggregate(expr)
            return expr, is_agg

        return cond, self._contains_aggregate(cond)

    def _resolve_lookup(
        self, key: str, value: Any
    ) -> tuple[ColumnElement[bool] | None, bool]:
        """Resolve a keyword lookup and detect if it involves an aggregate."""
        from .expressions import apply_lookup, parse_lookup

        field_name = key.split("__")[0]
        is_annotated = field_name in self._annotations

        if is_annotated:
            # Filters on calculated fields land in HAVING.
            col = self._annotations[field_name]
            _, lookup = parse_lookup(self.model, key)
        else:
            # Standard model attributes typically use WHERE.
            col, lookup = parse_lookup(self.model, key)

        if col is None:
            return None, False

        resolved_value = (
            value.resolve(self.model, _annotations=self._annotations)
            if isinstance(value, Resolvable)
            else value
        )

        expr = apply_lookup(col, lookup, resolved_value)
        # Identify if HAVING routing is triggered by the field or the value.
        is_agg = (
            is_annotated
            or self._contains_aggregate(value)
            or self._contains_aggregate(expr)
        )
        return expr, is_agg

    def _attach_condition(
        self, stmt: Select, expr: ColumnElement[bool], *, is_agg: bool
    ) -> Select:
        """Route an expression to the correct SQL clause (WHERE or HAVING)."""
        # Aggregates are illegal in WHERE and must use HAVING.
        return stmt.having(expr) if is_agg else stmt.where(expr)

    def _contains_aggregate(self, obj: Any) -> bool:
        """
        Recursively detect if a query element involves an aggregate function.

        Essential for routing conditions to either WHERE or HAVING clauses,
        as SQL prohibits aggregates in WHERE.
        """
        from sqlalchemy.sql.elements import BinaryExpression, BindParameter, Label
        from sqlalchemy.sql.functions import FunctionElement

        from .expressions import Aggregate, Q

        # Literals and bound parameters are terminal nodes.
        if isinstance(obj, (BindParameter, str, int, float, bool)) or obj is None:
            return False

        # flash_db aggregates and raw SA functions are terminal true.
        if isinstance(obj, (Aggregate, FunctionElement)):
            return True

        # Scan every branch of a Q object tree.
        if isinstance(obj, Q):
            return any(self._contains_aggregate(c) for c in obj.children)

        # Scan the value side of lookup pairs.
        if isinstance(obj, tuple) and len(obj) == 2:
            return self._contains_aggregate(obj[1])

        # Scan the underlying element of a Label.
        if isinstance(obj, Label):
            return self._contains_aggregate(obj.element)

        # Scan both operands of a binary expression.
        if isinstance(obj, BinaryExpression):
            return self._contains_aggregate(obj.left) or self._contains_aggregate(
                obj.right
            )

        # Traverse generic SQLAlchemy expression trees.
        get_children = getattr(obj, "get_children", None)
        if callable(get_children):
            return any(self._contains_aggregate(c) for c in get_children())  # pyright: ignore[reportGeneralTypeIssues]

        return False
