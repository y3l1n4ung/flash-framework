from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError

from .models import Model
from .queryset import QuerySet

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ColumnElement

    from .expressions import Q

T = TypeVar("T", bound=Model)
PrimaryKey = int | str | UUID


class ModelManager(Generic[T]):
    """
    Entry point for model-level database operations.

    Responsible for creating QuerySets and handling single-record actions.
    """

    def __init__(self, model: type[T]):
        self._model = model

    def _get_queryset(self) -> QuerySet[T]:
        """
        Return a fresh QuerySet instance for the model.
        """
        return QuerySet(self._model, select(self._model))

    def all(self) -> QuerySet[T]:
        """
        Return a QuerySet containing all records.
        """
        return self._get_queryset()

    def filter(
        self,
        *conditions: ColumnElement[bool] | Q,
        **kwargs: object,
    ) -> QuerySet[T]:
        """
        Return a filtered QuerySet based on provided conditions.
        """
        return self._get_queryset().filter(*conditions, **kwargs)

    def exclude(
        self, *conditions: ColumnElement[bool] | Q, **kwargs: object
    ) -> QuerySet[T]:
        """
        Return a QuerySet excluding records matching provided conditions.
        """
        return self._get_queryset().exclude(*conditions, **kwargs)

    def distinct(self, *criterion: Any) -> QuerySet[T]:
        """
        Return a QuerySet with DISTINCT criteria.
        """
        return self._get_queryset().distinct(*criterion)

    def order_by(self, *criterion: Any) -> QuerySet[T]:
        """
        Return a QuerySet with ORDER BY criteria.
        """
        return self._get_queryset().order_by(*criterion)

    def limit(self, count: int) -> QuerySet[T]:
        """
        Return a QuerySet with LIMIT criteria.
        """
        return self._get_queryset().limit(count)

    def offset(self, count: int) -> QuerySet[T]:
        """
        Return a QuerySet with OFFSET criteria.
        """
        return self._get_queryset().offset(count)

    def only(self, *fields: str) -> QuerySet[T]:
        """
        Return a QuerySet loading only specified fields.
        """
        return self._get_queryset().only(*fields)

    def defer(self, *fields: str) -> QuerySet[T]:
        """
        Return a QuerySet deferring specified fields.
        """
        return self._get_queryset().defer(*fields)

    def prefetch_related(self, *fields: str) -> QuerySet[T]:
        """
        Return a QuerySet with prefetch_related criteria.
        """
        return self._get_queryset().prefetch_related(*fields)

    async def latest(self, db: AsyncSession, field: str = "created_at") -> T | None:
        """
        Return the latest object in the table based on the given field.
        """
        return await self._get_queryset().latest(db, field)

    async def earliest(self, db: AsyncSession, field: str = "created_at") -> T | None:
        """
        Return the earliest object in the table based on the given field.
        """
        return await self._get_queryset().earliest(db, field)

    async def values(self, db: AsyncSession, *fields: str) -> list[dict[str, Any]]:
        """
        Return a list of dictionaries for the specified fields.
        """
        return await self._get_queryset().values(db, *fields)

    async def values_list(
        self, db: AsyncSession, *fields: str, flat: bool = False
    ) -> list[Any]:
        """
        Return a list of tuples for the specified fields.
        """
        return await self._get_queryset().values_list(db, *fields, flat=flat)

    async def get(
        self,
        db: AsyncSession,
        *conditions: ColumnElement[bool],
    ) -> T:
        """
        Retrieve a single object matching the given conditions.

        Args:
            db: The database session.
            *conditions: SQLAlchemy expressions or Q objects.

        Raises:
            ValueError: If no object matches or multiple objects match.

        Example:
            >>> user = await User.objects.get(db, User.id == 1)
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
            raise ValueError(
                msg,
            )

        return objs[0]

    async def get_by_pk(
        self,
        db: AsyncSession,
        pk: PrimaryKey,
        *,
        pk_column: str = "id",
    ) -> T:
        """
        Retrieve a single object by its primary key.
        """
        return await self.get(db, getattr(self._model, pk_column) == pk)

    async def exists(self, db: AsyncSession, *conditions: ColumnElement[bool]) -> bool:
        """
        Check if any records exist matching the given conditions.
        """
        return await self.filter(*conditions).exists(db)

    async def count(self, db: AsyncSession, *conditions: ColumnElement[bool]) -> int:
        """
        Return the total number of records matching the given conditions.
        """
        return await self.filter(*conditions).count(db)

    async def create(self, db: AsyncSession, **fields: Any) -> T:
        """
        Create and persist a new model instance.

        Args:
            db: The database session.
            **fields: Column values for the new instance.

        Example:
            >>> user = await User.objects.create(
            ...     db, name="John Doe", email="john@example.com"
            ... )
        """
        try:
            instance: T = self._model(**fields)
            db.add(instance)
            await db.commit()
            await db.refresh(instance)

        except SQLAlchemyError as e:
            await db.rollback()
            msg = f"Database error while creating {self._model.__name__}: {e}"
            raise RuntimeError(
                msg,
            ) from e
        else:
            return instance

    async def bulk_create(
        self, db: AsyncSession, objs: list[dict[str, Any]]
    ) -> list[T]:
        """
        Create multiple records in a single database round-trip.

        Args:
            db: The database session.
            objs: A list of dictionaries, each representing column values
                for a new record.

        Example:
            >>> users = await User.objects.bulk_create(db, [
            ...     {"name": "Alice"},
            ...     {"name": "Bob"},
            ... ])
        """
        if not objs:
            return []

        from sqlalchemy import insert

        stmt = insert(self._model).values(objs).returning(self._model)
        try:
            result = await db.execute(stmt)
            await db.commit()
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            await db.rollback()
            msg = f"Database error while bulk creating {self._model.__name__}: {e}"
            raise RuntimeError(msg) from e

    async def get_or_create(
        self,
        db: AsyncSession,
        defaults: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[T, bool]:
        """
        Look up an object with the given kwargs, creating one if necessary.
        Return a tuple of (object, created), where created is a boolean.
        """
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
        """
        Look up an object with the given kwargs, updating one if exists with defaults,
        otherwise creating one.
        Return a tuple of (object, created), where created is a boolean.
        """
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
        """
        Update a single record by primary key and return the updated instance.

        Raises:
            ValueError: If the record with the given PK does not exist.
            RuntimeError: If a database integrity or connection error occurs.
        """
        try:
            # Use getattr to allow for different PK column names if needed in future
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
            raise RuntimeError(
                msg,
            ) from e
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
        """
        Delete a single object by primary key and return the number of deleted rows.
        """
        column = getattr(self._model, pk_column)
        stmt = delete(self._model).where(column == pk)

        try:
            result = await db.execute(stmt)
            await db.commit()
            # Extract rowcount immediately after commit
            count = getattr(result, "rowcount", 0)
        except SQLAlchemyError as e:
            await db.rollback()
            msg = f"Database error while deleting {self._model.__name__}"
            raise RuntimeError(
                msg,
            ) from e
        except Exception:
            await db.rollback()
            raise

        if raise_if_missing and count == 0:
            msg = f"{self._model.__name__} with id {pk} not found"
            raise ValueError(msg)

        return count
