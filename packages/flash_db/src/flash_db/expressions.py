from __future__ import annotations

from abc import ABC
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Mapping,
    Protocol,
    cast,
    runtime_checkable,
)

from sqlalchemy import and_, func, not_, or_

if TYPE_CHECKING:
    from sqlalchemy.orm import InstrumentedAttribute
    from sqlalchemy.sql import ColumnElement

    from .models import Model


@runtime_checkable
class Resolvable(Protocol):
    """Protocol for objects resolvable into SQLAlchemy expressions."""

    def resolve(
        self,
        model: type["Model"],
        _annotations: Mapping[str, "ColumnElement[Any]"] | None = None,
    ) -> "ColumnElement[Any] | None":
        """Resolve the object into a SQLAlchemy expression."""
        ...


def parse_lookup(
    model: type["Model"], key: str
) -> tuple["ColumnElement[Any] | None", str, str]:
    """
    Parse a lookup key into (column, operator, field_name).

    Supported format: 'field' or 'field__lookup' (e.g., 'price' or 'price__gt').
    Nested lookups across relationships (e.g., 'author__name') are not
    currently supported and will raise a ValueError.
    """
    parts = key.split("__")
    if len(parts) > 2:
        msg = (
            f"Unsupported lookup '{key}'. Nested lookups across relationships "
            f"are not currently supported."
        )
        raise ValueError(msg)

    field_name = parts[0]
    lookup = parts[1] if len(parts) > 1 else "exact"

    col = getattr(model, field_name, None)
    return col, lookup, field_name


def apply_lookup(col: Any, lookup: str, value: Any) -> "ColumnElement[bool]":
    """Apply a lookup operator to a SQLAlchemy column."""
    operators: dict[str, Callable[[Any, Any], "ColumnElement[bool]"]] = {
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
        "istartswith": lambda c, v: func.lower(c).startswith(func.lower(v)),
        "endswith": lambda c, v: c.endswith(v),
        "iendswith": lambda c, v: func.lower(c).endswith(func.lower(v)),
        "isnull": lambda c, v: c.is_(None) if v else c.isnot(None),
    }

    if lookup not in operators:
        supported = ", ".join(operators.keys())
        msg = f"Unsupported lookup '{lookup}'. Supported: {supported}"
        raise ValueError(msg)

    return operators[lookup](col, value)


class Q(Resolvable):
    """Encapsulates a query condition that can be combined using bitwise operators.

    Q objects can be combined using & (AND), | (OR), and ~ (NOT).
    """

    AND = "AND"
    OR = "OR"

    def __init__(
        self,
        *args: "Q | ColumnElement[bool]",
        _connector: str = AND,
        _negated: bool = False,
        **kwargs: object,
    ):
        """Initialize a Q object with positional and keyword conditions."""
        self.children: list["Q | ColumnElement[bool] | tuple[str, object]"] = list(
            args
        ) + list(kwargs.items())
        self.connector = _connector
        self.negated = _negated

    def __and__(self, other: "Q") -> "Q":
        return self._combine(other, self.AND)

    def __or__(self, other: "Q") -> "Q":
        return self._combine(other, self.OR)

    def __invert__(self) -> "Q":
        obj = Q()
        obj.children = self.children[:]
        obj.connector = self.connector
        obj.negated = not self.negated
        return obj

    def _combine(self, other: "Q", connector: str) -> "Q":
        if not isinstance(other, Q):
            msg = f"Cannot combine Q object with {type(other).__name__}"
            raise TypeError(msg)

        obj = Q(_connector=connector)
        obj.children = [self, other]
        return obj

    def resolve(
        self,
        model: type["Model"],
        _annotations: Mapping[str, "ColumnElement[Any]"] | None = None,
    ) -> "ColumnElement[Any] | None":
        """Resolve the Q object into a SQLAlchemy expression.

        Args:
            model: The model class to resolve against.
            _annotations: Optional dictionary of active query annotations.

        Returns:
            A SQLAlchemy boolean expression.
        """
        expressions: list["ColumnElement[bool]"] = []
        for child in self.children:
            if isinstance(child, Q):
                resolved = child.resolve(model, _annotations)
                if resolved is not None:
                    expressions.append(resolved)
            elif isinstance(child, tuple):
                key, value = child
                key = cast("str", key)
                col, lookup, field_name = parse_lookup(model, key)

                if _annotations and field_name in _annotations:
                    col = _annotations[field_name]

                if col is None:
                    msg = (
                        f"Field or annotation '{field_name}' not found on model "
                        f"{model.__name__}"
                    )
                    raise AttributeError(msg)

                if hasattr(value, "resolve"):
                    resolved_value = cast("Resolvable", value).resolve(
                        model, _annotations
                    )
                else:
                    resolved_value = value

                expressions.append(apply_lookup(col, lookup, resolved_value))
            else:
                expressions.append(cast("ColumnElement[bool]", child))

        if not expressions:
            return None

        clause = or_(*expressions) if self.connector == self.OR else and_(*expressions)
        return not_(clause) if self.negated else clause


class Aggregate(ABC, Resolvable):
    """Base class for SQL aggregate functions (Count, Sum, etc.)."""

    _func_name: str

    def __init__(self, field: str):
        self.field = field

    def resolve(
        self,
        model: type["Model"],
        _annotations: Mapping[str, "ColumnElement[Any]"] | None = None,
    ) -> "ColumnElement[Any]":
        """Resolve the aggregate into a SQLAlchemy function expression."""
        col: "ColumnElement[Any] | None" = None
        if _annotations and self.field in _annotations:
            col = _annotations[self.field]

        if col is None:
            col = getattr(model, self.field, None)

        if col is None:
            msg = (
                f"Field or annotation '{self.field}' not found on model "
                f"{model.__name__}"
            )
            raise AttributeError(msg)

        return getattr(func, self._func_name)(col)

    def get_joins(self, model: type["Model"]) -> list["InstrumentedAttribute[Any]"]:
        """Identify relationship attributes that must be joined for this aggregate."""
        from sqlalchemy.orm import RelationshipProperty

        attr = getattr(model, self.field, None)
        if (
            attr is not None
            and hasattr(attr, "property")
            and isinstance(attr.property, RelationshipProperty)
        ):
            return [cast("InstrumentedAttribute[Any]", attr)]
        return []


class Count(Aggregate):
    """SQL COUNT aggregate function."""

    _func_name = "count"

    def resolve(
        self,
        model: type["Model"],
        _annotations: Mapping[str, "ColumnElement[Any]"] | None = None,
    ) -> "ColumnElement[Any]":
        from sqlalchemy.orm import RelationshipProperty

        # Check annotations first
        col: "ColumnElement[Any] | None" = None
        if _annotations and self.field in _annotations:
            col = _annotations[self.field]

        if col is not None:
            return func.count(col)

        attr = getattr(model, self.field, None)
        if attr is None:
            msg = (
                f"Field or annotation '{self.field}' not found on model "
                f"{model.__name__}"
            )
            raise AttributeError(msg)

        if hasattr(attr, "property") and isinstance(
            attr.property, RelationshipProperty
        ):
            target_model = attr.property.mapper.class_
            return func.count(target_model.id)

        return func.count(attr)


class Sum(Aggregate):
    """SQL SUM aggregate function."""

    _func_name = "sum"


class Avg(Aggregate):
    """SQL AVG aggregate function."""

    _func_name = "avg"


class Max(Aggregate):
    """SQL MAX aggregate function."""

    _func_name = "max"


class Min(Aggregate):
    """SQL MIN aggregate function."""

    _func_name = "min"


class F(Resolvable):
    """Encapsulates a reference to a model field with arithmetic support."""

    name: str

    def __init__(self, name: str | InstrumentedAttribute[Any]):
        self.name = name if isinstance(name, str) else name.key
        self._ops: list[tuple[str, Any]] = []

    def __add__(self, other: Any) -> "F":
        new_f = F(self.name)
        new_f._ops = [*self._ops, ("+", other)]
        return new_f

    def __sub__(self, other: Any) -> "F":
        new_f = F(self.name)
        new_f._ops = [*self._ops, ("-", other)]
        return new_f

    def __mul__(self, other: Any) -> "F":
        new_f = F(self.name)
        new_f._ops = [*self._ops, ("*", other)]
        return new_f

    def __truediv__(self, other: Any) -> "F":
        new_f = F(self.name)
        new_f._ops = [*self._ops, ("/", other)]
        return new_f

    def resolve(
        self,
        model: type["Model"],
        _annotations: Mapping[str, "ColumnElement[Any]"] | None = None,
    ) -> "ColumnElement[Any] | None":
        # Check annotations first
        if _annotations and self.name in _annotations:
            res = _annotations[self.name]
        else:
            res = getattr(model, self.name, None)

        if res is None:
            msg = (
                f"Field or annotation '{self.name}' not found on model {model.__name__}"
            )
            raise AttributeError(msg)

        for op, other in self._ops:
            if hasattr(other, "resolve"):
                other = cast("Resolvable", other).resolve(model, _annotations)

            if other is None:
                msg = f"Operand resolved to None in F('{self.name}') expression"
                raise ValueError(msg)

            if op == "+":
                res = res + other
            elif op == "-":
                res = res - other
            elif op == "*":
                res = res * other
            elif op == "/":
                res = res / other
        return res
