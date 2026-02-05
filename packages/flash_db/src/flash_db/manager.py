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

    def filter(self, *conditions: ColumnElement[bool]) -> QuerySet[T]:
        """
        Return a filtered QuerySet based on provided conditions.
        """
        return self._get_queryset().filter(*conditions)

    def exclude(self, *conditions: ColumnElement[bool]) -> QuerySet[T]:
        """
        Return a QuerySet excluding records matching provided conditions.
        """
        return self._get_queryset().exclude(*conditions)

    def distinct(self, *criterion: Any) -> QuerySet[T]:
        """
        Return a QuerySet with DISTINCT criteria.
        """
        return self._get_queryset().distinct(*criterion)

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

    async def get(
        self,
        db: AsyncSession,
        *conditions: ColumnElement[bool],
    ) -> T:
        """
        Retrieve a single object matching the given conditions.

        Raises:
            ValueError: If no object matches or multiple objects match.
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

    async def create(self, db: AsyncSession, **fields: Any) -> T:
        """
        Create and persist a new model instance.
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
            return instance, False
        except ValueError:
            params = {**kwargs, **(defaults or {})}
            instance = await self.create(db, **params)
            return instance, True

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
            return instance, False
        except ValueError:
            params = {**kwargs, **(defaults or {})}
            instance = await self.create(db, **params)
            return instance, True

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
