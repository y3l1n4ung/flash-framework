from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
)

from .base import QuerySetBase, T

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement, Select


class QuerySetResolver(QuerySetBase[T]):
    """
    Internal logic for SQL condition and lookup resolution.

    This layer handles the translation of high-level query constructs (like Q
    objects and Django-style field lookups) into SQLAlchemy expressions, while
    automatically routing conditions to either WHERE or HAVING clauses.
    """

    def _resolve_condition(
        self, cond: ColumnElement[bool] | Any
    ) -> tuple[ColumnElement[bool] | None, bool]:
        """Resolve a positional condition and detect if it involves an aggregate."""
        from flash_db.expressions import Resolvable

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
        """
        Parse a Django-style keyword lookup and determine its SQL routing.

        This internal method breaks down lookups like 'price__gt' or
        'comments__count__gte' and determines whether the resulting expression
        belongs in a WHERE clause or a HAVING clause.

        Args:
            key: The lookup string (e.g., 'field_name__lookup_type').
            value: The value to compare against. Can be a literal or a Resolvable.

        Returns:
            A tuple of (SQLAlchemy expression, is_aggregate_boolean).

        Raises:
            ValueError: If the field or annotation name does not exist on the model.

        Notes:
            - Routing to HAVING is triggered if the field is an annotation or if
              the value/expression itself contains an aggregate.
        """
        from flash_db.expressions import Resolvable, apply_lookup, parse_lookup

        field_name = key.split("__")[0]
        is_annotated = field_name in self._annotations

        if is_annotated:
            # Annotations (calculated fields) MUST be filtered via HAVING.
            col = self._annotations[field_name]
            _, lookup = parse_lookup(self.model, key)
        else:
            # Standard columns are filtered via WHERE.
            col, lookup = parse_lookup(self.model, key)

        if col is None:
            msg = (
                f"Field or annotation '{field_name}' not found on model "
                f"{self.model.__name__}"
            )
            raise ValueError(msg)

        resolved_value = (
            value.resolve(self.model, _annotations=self._annotations)
            if isinstance(value, Resolvable)
            else value
        )

        expr = apply_lookup(col, lookup, resolved_value)

        # is_agg determines if we use .where() or .having().
        # An annotated field always triggers HAVING.
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

        This check is vital for SQL validity: standard SQL forbids aggregate
        functions (like SUM or COUNT) within a WHERE clause. This method
        identifies such elements so the QuerySet can route them to the
        HAVING clause instead.

        Args:
            obj: The object to inspect. Can be a Q object, a SQLAlchemy expression,
                a literal, or a Flash aggregate.

        Returns:
            True if the object or any of its children contains an aggregate function.

        Notes:
            - Performs a deep traversal of expression trees.
            - Recognizes both Flash-native `Aggregate` classes and raw
              SQLAlchemy `FunctionElement` types.
        """
        from sqlalchemy.sql.elements import BinaryExpression, BindParameter, Label
        from sqlalchemy.sql.functions import FunctionElement

        from flash_db.expressions import Aggregate, Q

        # Terminal nodes (literals) cannot be aggregates.
        if isinstance(obj, (BindParameter, str, int, float, bool)) or obj is None:
            return False

        # Direct Flash Aggregate classes.
        if isinstance(obj, Aggregate):
            return True

        # Check raw SQLAlchemy functions (e.g. func.count()).
        if isinstance(obj, FunctionElement):
            return obj.name.lower() in ("count", "sum", "avg", "max", "min")

        # Recursive check for logical groupings.
        if isinstance(obj, Q):
            return any(self._contains_aggregate(c) for c in obj.children)

        # Recursive check for lookup tuples (field, value).
        if isinstance(obj, tuple) and len(obj) == 2:
            return self._contains_aggregate(obj[1])

        # Labels wrap expressions; we check the underlying element.
        if isinstance(obj, Label):
            return self._contains_aggregate(obj.element)

        # Binary expressions (e.g., F("x") + F("y")) require checking both sides.
        if isinstance(obj, BinaryExpression):
            return self._contains_aggregate(obj.left) or self._contains_aggregate(
                obj.right
            )

        # Use SQLAlchemy's visitor pattern or child-traversal if available.
        get_children = getattr(obj, "get_children", None)
        if callable(get_children):
            return any(
                self._contains_aggregate(c)
                for c in get_children()  # pyright: ignore[reportGeneralTypeIssues]
            )

        return False
