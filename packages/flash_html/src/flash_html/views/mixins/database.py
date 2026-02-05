import inspect
from typing import Any

from fastapi import Depends
from flash_db.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession


class DatabaseMixin:
    """Inject an AsyncSession into the view via FastAPI dependency injection."""

    db: AsyncSession | None = None

    @classmethod
    def resolve_dependencies(
        cls,
        params: list[inspect.Parameter],
        **kwargs: Any,
    ) -> None:
        if not any(param.name == "db" for param in params):
            params.insert(
                0,
                inspect.Parameter(
                    name="db",
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=AsyncSession,
                    default=Depends(get_db),
                ),
            )

        super().resolve_dependencies(params, **kwargs)  # type: ignore[attr-defined]
