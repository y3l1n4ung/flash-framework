from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    cast,
)

from sqlalchemy.orm import joinedload, selectinload

from .resolver import QuerySetResolver, T

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement


class QuerySetConstruction(QuerySetResolver[T]):
    """
    Fluent API for building and composing QuerySet transformations.

    This layer implements the chaining methods (like filter, order_by, limit) that
    return a new QuerySet instance, allowing for the step-by-step construction of
    database queries.
    """

    def distinct(self, *criterion: Any) -> Any:
        """
        Add DISTINCT criteria to the query.

        Example:
            >>> articles = await Article.objects.distinct().fetch(db)
            # SELECT DISTINCT * FROM articles;
        """
        return self._clone(self._stmt.distinct(*criterion))

    def order_by(self, *criterion: Any) -> Any:
        """
        Add ORDER BY criteria to the query.

        Example:
            >>> Article.objects.order_by("title")
            # SELECT * FROM articles ORDER BY title ASC;

            >>> Article.objects.order_by(Article.id.desc())
            # SELECT * FROM articles ORDER BY id DESC;
        """
        return self._clone(self._stmt.order_by(*criterion))

    def limit(self, count: int) -> Any:
        """
        Limit the number of records returned.

        Example:
            >>> articles = await Article.objects.limit(10).fetch(db)
            # SELECT * FROM articles LIMIT 10;
        """
        return self._clone(self._stmt.limit(count))

    def offset(self, count: int) -> Any:
        """
        Apply an offset to the result set.

        Example:
            >>> articles = await Article.objects.offset(10).fetch(db)
            # SELECT * FROM articles OFFSET 10;
        """
        return self._clone(self._stmt.offset(count))

    def only(self, *fields: str) -> Any:
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

    def defer(self, *fields: str) -> Any:
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

    def select_related(self, *fields: str) -> Any:
        """
        Eagerly load related relationships using SQL JOINs.

        This method follows foreign key relationships, selecting additional
        related-object data when the query is executed. This results in a
        single, more complex query, but avoids subsequent "N+1" database
        queries when accessing the related objects.

        Args:
            *fields: Relationship field names to join.

        Returns:
            A new QuerySet instance with the join options applied.

        Notes:
            - Best for 1-to-1 or Many-to-1 relationships.
            - Uses SQLAlchemy's `joinedload` internally.

        Example:
            >>> # Single query fetches both articles and authors
            >>> articles = await Article.objects.select_related("author").fetch(db)
            >>> print(articles[0].author.name)  # No additional query triggered
        """
        stmt = self._stmt
        for field in fields:
            # Use JOIN to fetch related data in a single round-trip.
            stmt = stmt.options(joinedload(getattr(self.model, field)))
        return self._clone(stmt)

    def prefetch_related(self, *fields: str) -> Any:
        """
        Eagerly load related relationships using separate queries.

        This method performs a separate lookup for each relationship and
        does the "joining" in Python. This is more efficient than
        `select_related` for Many-to-Many or 1-to-Many relationships where
        a SQL join would result in a massive Cartesian product.

        Args:
            *fields: Relationship field names to prefetch.

        Returns:
            A new QuerySet instance with the prefetch options applied.

        Notes:
            - Best for Many-to-Many or 1-to-Many relationships.
            - Uses SQLAlchemy's `selectinload` internally.

        Example:
            >>> # One query for articles, one for all related tags
            >>> articles = await Article.objects.prefetch_related("tags").fetch(db)
            >>> print(articles[0].tags[0].name)  # No additional query triggered
        """
        stmt = self._stmt
        for field in fields:
            # Load relationships where JOINs would cause excessive row
            # multiplication.
            stmt = stmt.options(selectinload(getattr(self.model, field)))
        return self._clone(stmt)

    def filter(self, *conditions: Any, **kwargs: object) -> Any:
        """
        Add WHERE or HAVING criteria to the query.

        This method allows filtering the QuerySet using either raw SQLAlchemy
        expressions, Resolvable objects (like Q objects), or Django-style
        keyword lookups.

        Args:
            *conditions: Positional arguments for complex conditions, such as
                Q objects or raw SQLAlchemy expressions.
            **kwargs: Keyword lookups for simple attribute filtering
                (e.g., name="value", price__gt=10).

        Returns:
            A new QuerySet instance with the filters applied.

        Notes:
            - If a condition involves an aggregate (either from an annotation
              or an aggregate function), it's automatically routed to the
              SQL HAVING clause. Standard field filters go to WHERE.

        Examples:
            >>> # Keyword lookups
            >>> Product.objects.filter(name="A", price__gt=10)
            >>>
            >>> # Complex Q objects
            >>> Product.objects.filter(Q(price__lt=5) | Q(stock=0))
            >>>
            >>> # Filtering on annotations (routes to HAVING)
            >>> Product.objects.annotate(n=Count('revs')).filter(n__gt=5)
        """
        if not conditions and not kwargs:
            return self

        stmt = self._stmt

        # Positional conditions (like Q objects) are processed first.
        for cond in conditions:
            # _resolve_condition identifies if the expression contains aggregates.
            # This is critical because SQL prohibits aggregates in WHERE clauses.
            expr, is_agg = self._resolve_condition(cond)
            if expr is not None:
                # _attach_condition routes to .where() or .having() based on is_agg.
                stmt = self._attach_condition(stmt, expr, is_agg=is_agg)

        # Keyword lookups are processed next.
        for key, value in kwargs.items():
            # _resolve_lookup parses Django-style strings like
            # 'author__name__icontains'.
            expr, is_agg = self._resolve_lookup(key, value)
            if expr is not None:
                stmt = self._attach_condition(stmt, expr, is_agg=is_agg)

        return self._clone(stmt)

    def exclude(self, *conditions: Any, **kwargs: object) -> Any:
        """
        Add negative WHERE or HAVING criteria to the query.

        This method is the inverse of `filter()`. It excludes records that match
        the given criteria by wrapping them in a SQL `NOT` expression.

        Args:
            *conditions: Positional arguments for complex negative conditions.
            **kwargs: Keyword lookups for attribute exclusion.

        Returns:
            A new QuerySet instance with the negative filters applied.

        Notes:
            - Like `filter()`, it automatically routes aggregate-based
              exclusions to the HAVING clause.

        Examples:
            >>> # Exclude by attribute
            >>> Product.objects.exclude(price__gt=100)
            >>>
            >>> # Exclude by annotation (routes to HAVING)
            >>> Article.objects.annotate(n=Count('comments')).exclude(n__lt=1)
        """
        if not conditions and not kwargs:
            return self

        from sqlalchemy import not_

        stmt = self._stmt

        # Negate and apply positional conditions.
        for cond in conditions:
            expr, is_agg = self._resolve_condition(cond)
            if expr is not None:
                # We wrap the resolved expression in not_() to invert the logic
                # at the SQL level before routing to WHERE or HAVING.
                stmt = self._attach_condition(stmt, not_(expr), is_agg=is_agg)

        # Negate and apply keyword lookups.
        for key, value in kwargs.items():
            expr, is_agg = self._resolve_lookup(key, value)
            if expr is not None:
                stmt = self._attach_condition(stmt, not_(expr), is_agg=is_agg)

        return self._clone(stmt)

    def annotate(self, **kwargs: Any) -> Any:
        """
        Add calculated fields (aggregates or expressions) to each row in the QuerySet.

        Annotations allow you to perform SQL-level calculations and retrieve the
        results as part of the model instances. If an annotation uses a relationship,
        this method automatically injects the necessary LEFT OUTER JOINs.

        Args:
            **kwargs: Mapping of field names to Resolvable expressions (F, Count, etc.)
                or raw SQLAlchemy ColumnElements.

        Returns:
            A new QuerySet instance with the annotations applied.

        Notes:
            - Automatically adds a `GROUP BY` clause on the model's primary key
              if aggregates are detected and no group by exists.
            - Duplicate joins are avoided by checking the statement's existing setup.

        Examples:
            >>> # Calculate count of related objects
            >>> Article.objects.annotate(num_comments=Count("comments"))
            >>>
            >>> # Use arithmetic in annotations
            >>> Product.objects.annotate(discounted_price=F("price") * 0.9)
        """
        if not kwargs:
            return self

        from flash_db.expressions import Aggregate, Resolvable

        stmt = self._stmt
        new_annotations = dict(self._annotations)

        for key, expr in kwargs.items():
            if isinstance(expr, Resolvable):
                # Resolvables transform high-level field lookups into SQLAlchemy
                # constructs. We pass current annotations to allow expressions
                # to reference previously defined labels within the same query.
                resolved = expr.resolve(self.model, _annotations=new_annotations)
                if resolved is not None:
                    # Labels are essential for result extraction. fetch() uses these
                    # keys to map raw database values back to the Model instance.
                    label = resolved.label(key)
                    stmt = stmt.add_columns(label)
                    new_annotations[key] = label

                # relationship-based aggregates (e.g., Count("comments")) require
                # a JOIN to the related table. We use LEFT OUTER JOIN to ensure the
                # base model is returned even if the related set is empty.
                if isinstance(expr, Aggregate):
                    for join_attr in expr.get_joins(self.model):
                        # Inspecting internal join state prevents redundant SQL and
                        # "duplicate alias" errors if multiple annotations share
                        # the same relationship path.
                        if join_attr not in [
                            j[0]
                            for j in stmt._setup_joins  # pyright: ignore
                        ]:
                            stmt = stmt.outerjoin(join_attr)
            else:
                # Direct support for raw SQLAlchemy constructs (e.g., func.now())
                # for users who need to bypass the Flash expression system.
                label = cast("ColumnElement[Any]", expr).label(key)
                stmt = stmt.add_columns(label)
                new_annotations[key] = label

        # SQL standard requires non-aggregated columns to be present in the
        # GROUP BY clause when aggregate functions are used. Grouping by the
        # primary key is the most efficient way to collapse the result set
        # back to unique model instances while satisfying SQL validity.
        #
        # SQL Example:
        #     SELECT users.*, count(posts.id) FROM users
        #     JOIN posts ON ... GROUP BY users.id;
        if not stmt._group_by_clauses:
            stmt = stmt.group_by(*self.model.__table__.primary_key)

        return self.__class__(self.model, stmt, _annotations=new_annotations)
