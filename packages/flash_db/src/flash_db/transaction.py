from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Any, Awaitable, Callable, ParamSpec, Self, TypeVar

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from sqlalchemy.ext.asyncio import AsyncSession

P = ParamSpec("P")
T = TypeVar("T")


class Atomic:
    """
    Async database transaction manager with nested transaction support.

    Works as:
    - async context manager
    - decorator

    Automatically:
    - begins a transaction
    - commits on success
    - rolls back on exception
    - uses SAVEPOINT when already inside a transaction

    This behavior mirrors Django's ``transaction.atomic``.

    Args:
        db: SQLAlchemy AsyncSession instance.

    Examples:
        >>> async with atomic(db):
        ...     await repo.create_user(db, user)

        >>> @atomic(db)
        ... async def create():
        ...     await repo.create_user(db, user)
        ...
        >>> await create()
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize atomic manager.

        Args:
            db: Active AsyncSession used for transaction control.
        """
        self.db = db
        self._cm: AbstractAsyncContextManager[Any] | None = None

    def _get_transaction_cm(self) -> AbstractAsyncContextManager[Any]:
        """
        Select correct transaction strategy.

        Returns:
            begin()        -> new top-level transaction
            begin_nested() -> SAVEPOINT for nested usage
        """
        if self.db.in_transaction():
            return self.db.begin_nested()
        return self.db.begin()

    async def __aenter__(self) -> Self:
        """
        Enter async transaction block.

        Returns:
            Self for optional usage inside the block.
        """
        self._cm = self._get_transaction_cm()
        await self._cm.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """
        Exit transaction block.

        Behavior:
            - commit if no exception
            - rollback if exception raised
        """
        if self._cm:
            await self._cm.__aexit__(exc_type, exc, tb)

    def __call__(self, func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        """
        Allow usage as a decorator.

        Wraps the function in a transaction automatically.

        Args:
            func: Async function to run atomically.

        Returns:
            Wrapped async function.

        Example:
            >>> @atomic(db)
            ... async def create_user():
            ...     await repo.create()
        """

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            async with Atomic(self.db):
                return await func(*args, **kwargs)

        return wrapper


def atomic(db: AsyncSession) -> Atomic:
    """
    Factory helper for creating an Atomic manager.

    Args:
        db: SQLAlchemy AsyncSession.

    Returns:
        Atomic instance.

    Examples:
        >>> async with atomic(db):
        ...     await do_work()

        >>> @atomic(db)
        ... async def task():
        ...     ...
    """
    return Atomic(db)
