from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError

from .models import Model
from .queryset import QuerySet

if TYPE_CHECKING:
    from sqlalchemy import Table
    from sqlalchemy.engine import Connection, Engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ColumnElement

T = TypeVar("T", bound=Model)
PrimaryKey = int | str | UUID


class ModelManager(Generic[T]):
    """Entry point for model-level database operations.

    Provides high-level methods for creating, retrieving, and updating model
    instances, and acts as a gateway to building QuerySets.
    """

    def __init__(self, model: type[T]):
        """Initialize the manager with a model class."""
        self._model = model

    def _get_queryset(self) -> QuerySet[T]:
        """Return a fresh QuerySet instance for the model."""
        return QuerySet(self._model, select(self._model))

    def all(self) -> QuerySet[T]:
        """Return a QuerySet containing all records for this model."""
        return self._get_queryset()

    def filter(
        self,
        *conditions: ColumnElement[bool],
        **kwargs: object,
    ) -> QuerySet[T]:
        """Return a QuerySet filtered by the provided conditions.

        Args:
            *conditions: Positional SQLAlchemy expressions.
            **kwargs: Simple equality keyword lookups.

        Returns:
            A new QuerySet with filters applied.
        """
        return self._get_queryset().filter(*conditions, **kwargs)

    def exclude(
        self, *conditions: ColumnElement[bool], **kwargs: object
    ) -> QuerySet[T]:
        """Return a QuerySet excluding records matching provided conditions.

        Args:
            *conditions: Positional conditions to negate.
            **kwargs: Keyword lookups to negate.

        Returns:
            A new QuerySet with negated filters applied.
        """
        return self._get_queryset().exclude(*conditions, **kwargs)

    def distinct(self, *criterion: Any) -> QuerySet[T]:
        """Return a QuerySet with DISTINCT criteria applied."""
        return self._get_queryset().distinct(*criterion)

    def order_by(self, *criterion: Any) -> QuerySet[T]:
        """Return a QuerySet with an ORDER BY clause applied."""
        return self._get_queryset().order_by(*criterion)

    def limit(self, count: int) -> QuerySet[T]:
        """Return a QuerySet restricted by a LIMIT clause."""
        return self._get_queryset().limit(count)

    def offset(self, count: int) -> QuerySet[T]:
        """Return a QuerySet restricted by an OFFSET clause."""
        return self._get_queryset().offset(count)

    def only(self, *fields: str) -> QuerySet[T]:
        """Return a QuerySet loading only the specified fields."""
        return self._get_queryset().only(*fields)

    def defer(self, *fields: str) -> QuerySet[T]:
        """Return a QuerySet deferring the specified fields."""
        return self._get_queryset().defer(*fields)

    def select_related(self, *fields: str) -> QuerySet[T]:
        """Return a QuerySet with select_related JOINs applied."""
        return self._get_queryset().select_related(*fields)

    def prefetch_related(self, *fields: str) -> QuerySet[T]:
        """Return a QuerySet with prefetch_related queries configured."""
        return self._get_queryset().prefetch_related(*fields)

    async def first(self, db: AsyncSession) -> T | None:
        """Execute query and return the first matching instance or None."""
        return await self._get_queryset().first(db)

    async def last(self, db: AsyncSession) -> T | None:
        """Execute query and return the last record by ID or None."""
        return await self._get_queryset().last(db)

    async def latest(self, db: AsyncSession, field: str = "created_at") -> T | None:
        """Execute query and return the latest record by the specified field."""
        return await self._get_queryset().latest(db, field)

    async def earliest(self, db: AsyncSession, field: str = "created_at") -> T | None:
        """Execute query and return the earliest record by the specified field."""
        return await self._get_queryset().earliest(db, field)

    async def values(self, db: AsyncSession, *fields: str) -> list[dict[str, Any]]:
        """Return raw dictionaries for the specified fields of all records."""
        return await self._get_queryset().values(db, *fields)

    async def values_list(
        self, db: AsyncSession, *fields: str, flat: bool = False
    ) -> list[Any]:
        """Return raw tuples or flat values for the specified fields."""
        return await self._get_queryset().values_list(db, *fields, flat=flat)

    async def get(
        self,
        db: AsyncSession,
        *conditions: ColumnElement[bool],
    ) -> T:
        """Retrieve a single instance matching the provided conditions.

        Args:
            db: The database session.
            *conditions: Filter expressions.

        Returns:
            The single matching model instance.

        Raises:
            ValueError: If zero or more than one record matches.
        """
        stmt = select(self._model).where(*conditions).limit(2)
        result = await db.execute(stmt)
        objs = cast("list[T]", result.scalars().all())

        if not objs:
            msg = f"{self._model.__name__} matching query does not exist"
            raise ValueError(msg)
        if len(objs) > 1:
            msg = (
                f"get() returned more than one {self._model.__name__} "
                f"-- it returned {len(objs)}!"
            )
            raise ValueError(msg)

        return objs[0]

    async def get_by_pk(
        self,
        db: AsyncSession,
        pk: PrimaryKey,
        *,
        pk_column: str = "id",
    ) -> T:
        """Retrieve a single instance by its primary key."""
        return await self.get(db, getattr(self._model, pk_column) == pk)

    async def exists(self, db: AsyncSession, *conditions: ColumnElement[bool]) -> bool:
        """Return True if any records match the given conditions."""
        return await self._get_queryset().filter(*conditions).exists(db)

    async def count(self, db: AsyncSession, *conditions: ColumnElement[bool]) -> int:
        """Return the count of records matching the given conditions."""
        return await self._get_queryset().filter(*conditions).count(db)

    async def create(self, db: AsyncSession, **fields: Any) -> T:
        """Create and persist a new model instance.

        Args:
            db: The database session.
            **fields: Column values for the new record.

        Returns:
            The newly created and refreshed model instance.

        Raises:
            RuntimeError: If a database error occurs.
        """
        try:
            instance: T = self._model(**fields)
            db.add(instance)
            await db.commit()
            await db.refresh(instance)

        except SQLAlchemyError as e:
            await db.rollback()
            msg = f"Database error while creating {self._model.__name__}: {e}"
            raise RuntimeError(msg) from e
        else:
            return instance

    async def _get_bind(self, db: AsyncSession) -> Connection | Engine:
        """Robustly retrieve the database connection or engine bind."""
        bind = db.get_bind()
        if inspect.isawaitable(bind):
            return cast("Connection | Engine", await bind)
        return cast("Connection | Engine", bind)

    async def bulk_create(
        self,
        db: AsyncSession,
        objs: list[dict[str, Any]],
        *,
        ignore_conflicts: bool = False,
    ) -> list[T]:
        """Create multiple records in a single batch.

        Args:
            db: The database session.
            objs: List of dictionaries with column values.
            ignore_conflicts: If True, skip existing records (dialect-dependent).

        Returns:
            List of created model instances (limited support for auto-generated IDs).
        """
        if not objs:
            return []

        from sqlalchemy import insert
        from sqlalchemy.dialects import mysql, postgresql, sqlite

        bind = await self._get_bind(db)
        dialect_name = bind.dialect.name

        insert_map: dict[str, Any] = {
            "postgresql": postgresql.insert,
            "sqlite": sqlite.insert,
            "mysql": mysql.insert,
        }
        insert_func = insert_map.get(dialect_name, insert)

        stmt = insert_func(self._model).values(objs)

        if ignore_conflicts:
            if dialect_name in ("postgresql", "sqlite"):
                stmt = stmt.on_conflict_do_nothing()
            elif dialect_name == "mysql":
                stmt = stmt.prefix_with("IGNORE")

        try:
            if getattr(bind.dialect, "insert_returning", False):
                stmt = stmt.returning(self._model)
                result = await db.execute(stmt)
                await db.commit()
                return list(result.scalars().all())

            await db.execute(stmt)
            await db.commit()
            return [self._model(**obj) for obj in objs]

        except SQLAlchemyError as e:
            await db.rollback()
            msg = f"Database error while bulk creating {self._model.__name__}: {e}"
            raise RuntimeError(msg) from e

    async def bulk_update(
        self, db: AsyncSession, objs: list[T], fields: list[str]
    ) -> int:
        """Update multiple records in a single batch using ID matching.

        Args:
            db: The database session.
            objs: List of model instances with updated values.
            fields: The names of the columns to update.

        Returns:
            The number of records updated.
        """
        if not objs or not fields:
            return 0

        from sqlalchemy import bindparam

        update_data = [
            {"b_id": obj.id, **{f: getattr(obj, f) for f in fields}} for obj in objs
        ]

        table = cast("Table", self._model.__table__)
        stmt = (
            update(table)
            .where(table.c.id == bindparam("b_id"))
            .values({f: bindparam(f) for f in fields})
        )

        try:
            result = await db.execute(stmt, update_data)
            await db.commit()
            return getattr(result, "rowcount", 0)
        except SQLAlchemyError as e:
            await db.rollback()
            msg = f"Database error while bulk updating {self._model.__name__}: {e}"
            raise RuntimeError(msg) from e

    async def get_or_create(
        self,
        db: AsyncSession,
        defaults: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[T, bool]:
        """Get an existing record or create one if it doesn't exist."""
        try:
            conditions = [getattr(self._model, k) == v for k, v in kwargs.items()]
            instance = await self.get(db, *conditions)
        except ValueError:
            params = {**kwargs, **(defaults or {})}
            instance = await self.create(db, **params)
            return instance, True
        else:
            return instance, False

    async def update_or_create(
        self,
        db: AsyncSession,
        defaults: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[T, bool]:
        """Update an existing record or create one if it doesn't exist."""
        try:
            conditions = [getattr(self._model, k) == v for k, v in kwargs.items()]
            instance = await self.get(db, *conditions)
            if defaults:
                instance = await self.update(db, pk=instance.id, **defaults)
        except ValueError:
            params = {**kwargs, **(defaults or {})}
            instance = await self.create(db, **params)
            return instance, True
        else:
            return instance, False

    async def update(self, db: AsyncSession, pk: Any, **fields: Any) -> T:
        """Update a single record by primary key."""
        try:
            pk_col = self._model.id
            stmt = (
                update(self._model)
                .where(pk_col == pk)
                .values(**fields)
                .returning(self._model)
            )

            result = await db.execute(stmt)
            instance = result.scalar_one_or_none()

            if instance is not None:
                await db.commit()

        except SQLAlchemyError as e:
            await db.rollback()
            msg = f"Database error while updating {self._model.__name__}"
            raise RuntimeError(msg) from e
        except Exception:
            await db.rollback()
            raise

        if instance is None:
            msg = f"{self._model.__name__} with id {pk} not found"
            raise ValueError(msg)
        return cast("T", instance)

    async def delete_by_pk(
        self,
        db: AsyncSession,
        pk: Any,
        *,
        pk_column: str = "id",
        raise_if_missing: bool = False,
    ) -> int:
        """Delete a single record by primary key."""
        column = getattr(self._model, pk_column)
        stmt = delete(self._model).where(column == pk)

        try:
            result = await db.execute(stmt)
            await db.commit()
            count = getattr(result, "rowcount", 0)
        except SQLAlchemyError as e:
            await db.rollback()
            msg = f"Database error while deleting {self._model.__name__}"
            raise RuntimeError(msg) from e
        except Exception:
            await db.rollback()
            raise

        if raise_if_missing and count == 0:
            msg = f"{self._model.__name__} with id {pk} not found"
            raise ValueError(msg)

        return count
