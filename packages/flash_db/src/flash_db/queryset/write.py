from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
)

from sqlalchemy import delete, update

from .execution import QuerySetExecution, T

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class QuerySetWrite(QuerySetExecution[T]):
    """
    Bulk operations that modify data in the database.

    This layer handles bulk UPDATE and DELETE statements efficiently by
    operating directly on the database using the QuerySet's existing filters.
    """

    async def update(self, db: AsyncSession, **values: Any) -> int:
        """
        Execute bulk update on the QuerySet.

        This method performs a single SQL UPDATE statement targeting all
        records currently matched by the QuerySet filters.

        Args:
            db: The asynchronous SQLAlchemy session.
            **values: Field-value pairs to update. Values can be literals,
                F() expressions, or other Resolvables.

        Returns:
            The number of rows affected by the update.

        Raises:
            ValueError: If the QuerySet has no filters, to prevent accidental
                full-table updates.

        Notes:
            - This is a database-level update; it does not trigger any
              model-level `save()` methods or signals.
            - F() expressions are resolved to SQL expressions (e.g.,
              `price = price + 10`).

        Example:
            >>> # Simple update
            >>> await Article.objects.filter(id=1).update(db, title="New")
            >>>
            >>> # Update with F expression
            >>> await Product.objects.filter(category="sale").update(
            ...     db, price=F("price") * 0.9)
        """
        from flash_db.expressions import Resolvable

        where_clause = self._stmt._where_criteria
        # Safety check: update() without filter() is extremely dangerous in
        # production environments.
        if not where_clause:
            msg = "Refusing to update without filters"
            raise ValueError(msg)

        resolved_values = {
            k: v.resolve(self.model, _annotations=self._annotations)
            if isinstance(v, Resolvable)
            else v
            for k, v in values.items()
        }

        stmt = update(self.model).where(*where_clause).values(resolved_values)
        result = await db.execute(stmt)
        return getattr(result, "rowcount", 0)

    async def delete(self, db: AsyncSession) -> int:
        """
        Delete all records matched by the query.

        This method executes a single SQL DELETE statement against the
        database for all rows matched by the current QuerySet filters.

        Args:
            db: The asynchronous SQLAlchemy session.

        Returns:
            The number of rows deleted.

        Raises:
            ValueError: If the QuerySet has no filters, to prevent accidental
                full-table deletions.

        Notes:
            - This is a direct database-level deletion; it does not trigger
              any model-level `delete()` methods or signals.

        Example:
            >>> # Delete specific records
            >>> await Article.objects.filter(status="spam").delete(db)
        """
        where_clause = self._stmt._where_criteria
        # Safety check: delete() without filters could wipe an entire table.
        if not where_clause:
            msg = "Refusing to delete without filters"
            raise ValueError(msg)

        stmt = delete(self.model).where(*where_clause)
        result = await db.execute(stmt)
        return getattr(result, "rowcount", 0)
