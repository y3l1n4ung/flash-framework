from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import and_, not_, or_

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement

    from .models import Model


class Q:
    """
    Q objects can be combined using & (AND), | (OR), and ~ (NOT) operators.

    Example:
        >>> # Get users named 'Admin' OR with ID 1
        >>> User.objects.filter(Q(name="Admin") | Q(id=1))
        >>>
        >>> # Get users NOT named 'Guest'
        >>> User.objects.filter(~Q(name="Guest"))
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

    def resolve(self, model: type[Model]) -> ColumnElement[bool] | None:
        """
        Resolve the Q object into a SQLAlchemy expression for the given model.
        """
        expressions: list[ColumnElement[bool]] = []
        for child in self.children:
            if isinstance(child, Q):
                resolved = child.resolve(model)
                if resolved is not None:
                    expressions.append(resolved)
            elif isinstance(child, tuple):
                key, value = child
                expressions.append(getattr(model, str(key)) == value)
            else:
                expressions.append(child)

        if not expressions:
            return None

        clause = or_(*expressions) if self.connector == self.OR else and_(*expressions)

        return not_(clause) if self.negated else clause
