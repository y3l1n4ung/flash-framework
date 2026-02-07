from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, cast

from sqlalchemy import and_, func, not_, or_

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement

    from .models import Model


class Resolvable(Protocol):
    """Protocol for objects resolvable into SQLAlchemy expressions."""

    def resolve(
        self, model: type[Model], _annotations: dict[str, Any] | None = None
    ) -> Any:
        """Resolve the object into a SQLAlchemy expression."""
        ...


def parse_lookup(model: type[Model], key: str) -> tuple[Any, str]:
    """Parse a Django-style lookup key into (column, operator)."""
    parts = key.split("__")
    field_name = parts[0]
    lookup = parts[1] if len(parts) > 1 else "exact"

    col = getattr(model, field_name, None)
    return col, lookup


def apply_lookup(col: Any, lookup: str, value: Any) -> Any:
    """Apply a lookup operator to a SQLAlchemy column."""
    operators = {
        "exact": lambda c, v: c == v,
        "iexact": lambda c, v: func.lower(c) == func.lower(v),
        "contains": lambda c, v: c.contains(v),
        "icontains": lambda c, v: func.lower(c).contains(func.lower(v)),
        "gt": lambda c, v: c > v,
        "gte": lambda c, v: c >= v,
        "lt": lambda c, v: c < v,
        "lte": lambda c, v: c <= v,
        "in": lambda c, v: c.in_(v),
        "startswith": lambda c, v: c.startswith(v),
        "istartswith": lambda c, v: c.istartswith(v),
        "endswith": lambda c, v: c.endswith(v),
        "iendswith": lambda c, v: c.iendswith(v),
        "isnull": lambda c, v: c.is_(None) if v else c.isnot(None),
    }

    op = operators.get(lookup)
    if not op:
        return col == value

    return op(col, value)


class Q:
    """Encapsulates a query condition that can be combined using bitwise operators.

    Q objects can be combined using & (AND), | (OR), and ~ (NOT).
    """

    AND = "AND"
    OR = "OR"

    def __init__(
        self,
        *args: Q | ColumnElement[bool],
        _connector: str = AND,
        _negated: bool = False,
        **kwargs: object,
    ):
        """Initialize a Q object with positional and keyword conditions."""
        self.children: list[Q | ColumnElement[bool] | tuple[str, object]] = list(
            args
        ) + list(kwargs.items())
        self.connector = _connector
        self.negated = _negated

    def __and__(self, other: Q) -> Q:
        return self._combine(other, self.AND)

    def __or__(self, other: Q) -> Q:
        return self._combine(other, self.OR)

    def __invert__(self) -> Q:
        obj = Q()
        obj.children = self.children[:]
        obj.connector = self.connector
        obj.negated = not self.negated
        return obj

    def _combine(self, other: Q, connector: str) -> Q:
        if not isinstance(other, Q):
            msg = f"Cannot combine Q object with {type(other).__name__}"
            raise TypeError(msg)

        obj = Q(_connector=connector)
        obj.children = [self, other]
        return obj

    def resolve(
        self, model: type[Model], _annotations: dict[str, Any] | None = None
    ) -> ColumnElement[bool] | None:
        """Resolve the Q object into a SQLAlchemy expression.

        Args:
            model: The model class to resolve against.
            _annotations: Optional dictionary of active query annotations.

        Returns:
            A SQLAlchemy boolean expression or None if empty.
        """
        expressions: list[ColumnElement[bool]] = []
        for child in self.children:
            if isinstance(child, Q):
                resolved = child.resolve(model, _annotations)
                if resolved is not None:
                    expressions.append(resolved)
            elif isinstance(child, tuple):
                key, value = child
                key = cast("str", key)
                col, lookup = parse_lookup(model, key)
                field_name = key.split("__")[0]

                if _annotations and field_name in _annotations:
                    col = _annotations[field_name]

                if col is None:
                    col = getattr(model, field_name)

                if hasattr(value, "resolve"):
                    resolved_value = cast("Resolvable", value).resolve(
                        model, _annotations
                    )
                else:
                    resolved_value = value

                expressions.append(apply_lookup(col, lookup, resolved_value))
            else:
                expressions.append(child)

        if not expressions:
            return None

        clause = or_(*expressions) if self.connector == self.OR else and_(*expressions)
        return not_(clause) if self.negated else clause


class Aggregate:
    """Base class for SQL aggregate functions (Count, Sum, etc.)."""

    def __init__(self, field: str):
        self.field = field

    def resolve(
        self, model: type[Model], _annotations: dict[str, Any] | None = None
    ) -> Any:
        """Resolve the aggregate into a SQLAlchemy function expression."""
        raise NotImplementedError

    def get_joins(self, model: type[Model]) -> list[Any]:
        """Identify relationship attributes that must be joined for this aggregate."""
        from sqlalchemy.orm import RelationshipProperty

        attr = getattr(model, self.field, None)
        if (
            attr is not None
            and hasattr(attr, "property")
            and isinstance(attr.property, RelationshipProperty)
        ):
            return [attr]
        return []


class Count(Aggregate):
    """SQL COUNT aggregate function."""

    def resolve(
        self, model: type[Model], _annotations: dict[str, Any] | None = None
    ) -> Any:
        from sqlalchemy import func
        from sqlalchemy.orm import RelationshipProperty

        attr = getattr(model, self.field)
        if hasattr(attr, "property") and isinstance(
            attr.property, RelationshipProperty
        ):
            target_model = attr.property.mapper.class_
            return func.count(target_model.id)

        return func.count(attr)


class Sum(Aggregate):
    """SQL SUM aggregate function."""

    def resolve(
        self, model: type[Model], _annotations: dict[str, Any] | None = None
    ) -> Any:
        from sqlalchemy import func

        return func.sum(getattr(model, self.field))


class Avg(Aggregate):
    """SQL AVG aggregate function."""

    def resolve(
        self, model: type[Model], _annotations: dict[str, Any] | None = None
    ) -> Any:
        from sqlalchemy import func

        return func.avg(getattr(model, self.field))


class Max(Aggregate):
    """SQL MAX aggregate function."""

    def resolve(
        self, model: type[Model], _annotations: dict[str, Any] | None = None
    ) -> Any:
        from sqlalchemy import func

        return func.max(getattr(model, self.field))


class Min(Aggregate):
    """SQL MIN aggregate function."""

    def resolve(
        self, model: type[Model], _annotations: dict[str, Any] | None = None
    ) -> Any:
        from sqlalchemy import func

        return func.min(getattr(model, self.field))


class F:
    """Encapsulates a reference to a model field with arithmetic support."""

    def __init__(self, name: str):
        self.name = name
        self._ops: list[tuple[str, Any]] = []

    def __add__(self, other: Any) -> F:
        new_f = F(self.name)
        new_f._ops = [*self._ops, ("+", other)]
        return new_f

    def __sub__(self, other: Any) -> F:
        new_f = F(self.name)
        new_f._ops = [*self._ops, ("-", other)]
        return new_f

    def __mul__(self, other: Any) -> F:
        new_f = F(self.name)
        new_f._ops = [*self._ops, ("*", other)]
        return new_f

    def __truediv__(self, other: Any) -> F:
        new_f = F(self.name)
        new_f._ops = [*self._ops, ("/", other)]
        return new_f

    def resolve(
        self, model: type[Model], _annotations: dict[str, Any] | None = None
    ) -> Any:
        res = getattr(model, self.name)
        for op, other in self._ops:
            if hasattr(other, "resolve"):
                other = cast("Resolvable", other).resolve(model, _annotations)

            if op == "+":
                res = res + other
            elif op == "-":
                res = res - other
            elif op == "*":
                res = res * other
            elif op == "/":
                res = res / other
        return res
