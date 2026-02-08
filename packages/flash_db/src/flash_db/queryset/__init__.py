from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    TypeVar,
)

from .write import QuerySetWrite

if TYPE_CHECKING:
    from flash_db.models import Model


T = TypeVar("T", bound="Model")


class QuerySet(QuerySetWrite[T]):
    """
    Lazy, immutable query builder for a specific ORM model.

    A QuerySet wraps a SQLAlchemy ``Select`` statement and allows query
    composition without executing SQL immediately. Each transformation
    (filter, order_by, annotate, etc.) returns a new QuerySet instance,
    preserving immutability.

    Execution happens only through terminal methods such as:
        - fetch()
        - first()
        - count()
        - update()
        - delete()
        - aggregate()

    This design mirrors Django's QuerySet semantics while leveraging
    SQLAlchemy's expression system.

    Notes:
        - QuerySets are safe to reuse and chain.
        - Methods never mutate the original instance.
        - SQL is emitted only when an async execution method is called.

    Examples:
        >>> qs = Article.objects.filter(status="published")
        >>> qs = qs.order_by("-id").limit(10)
        >>> articles = await qs.fetch(db)

        >>> # Aggregation
        >>> await Article.objects.aggregate(db, total=func.count())
    """
