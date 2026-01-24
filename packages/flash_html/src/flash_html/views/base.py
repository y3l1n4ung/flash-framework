import inspect
from typing import Any, Callable, ClassVar, Coroutine, cast

from fastapi import Depends, Request, Response
from fastapi.responses import PlainTextResponse
from flash_db.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession


class View:
    """
    Async Class-Based View Root with FastAPI Dependency Injection Support.

    This class serves as the foundation for all views. It handles HTTP method
    dispatching and integrates seamlessly with FastAPI by preserving method
    signatures for dependency injection.

    Example:
        >>> class MyView(View):
        ...     async def get(self, request: Request, name: str = "World"):
        ...         return Response(f"Hello, {name}")
        >>>
        >>> app.add_api_route("/hello/{name}", MyView.as_view())
    """

    http_method_names: ClassVar[list[str]] = [
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "trace",
    ]

    request: Request
    kwargs: dict[str, Any]

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize the view instance with configuration overrides.
        """
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def as_view(cls, **initkwargs: Any) -> Callable[..., Coroutine[Any, Any, Response]]:
        """
        Create a FastAPI-compatible endpoint callable.

        This method validates attributes and reconstructs the function signature
        to support FastAPI's dependency injection system.

        Args:
            **initkwargs: Attributes to override on the view instance.

        Returns:
            Callable: An async function used as the FastAPI route handler.
        """
        # 1. Validate initkwargs against class attributes
        for key in initkwargs:
            if not hasattr(cls, key):
                raise TypeError(
                    f"{cls.__name__}() received an invalid keyword {key!r}. "
                    f"as_view() only accepts arguments that are already attributes "
                    f"of the class."
                )

        async def view(request: Request, **kwargs: Any) -> Response:
            self = cls(**initkwargs)
            self.request = request

            # Extract database session if provided by FastAPI injection
            db = kwargs.pop("db", None)
            if db is not None:
                setattr(self, "db", db)

            # Merge path parameters and additional kwargs
            self.kwargs = {**request.path_params, **kwargs}

            return await self.dispatch(**kwargs)

        view.__doc__ = cls.__doc__
        view.__module__ = cls.__module__
        view.__name__ = cls.__name__

        handler = None
        for method_name in cls.http_method_names:
            if hasattr(cls, method_name):
                potential_handler = getattr(cls, method_name)
                if potential_handler.__name__ != "http_method_not_allowed":
                    handler = potential_handler
                    break

        if handler:
            sig = inspect.signature(handler)
            # Exclude 'self', '*args', and '**kwargs' from the FastAPI signature
            new_params = [
                p
                for p in sig.parameters.values()
                if p.name != "self"
                and p.kind
                not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
            ]

            param_names = [p.name for p in new_params]

            # Ensure 'request' is present for FastAPI
            if "request" not in param_names:
                new_params.insert(
                    0,
                    inspect.Parameter(
                        name="request",
                        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=Request,
                    ),
                )

            # Auto-inject DB session if the view defines a 'model' (DB-bound views)
            if "db" not in param_names and hasattr(cls, "model"):
                new_params.insert(
                    0,
                    inspect.Parameter(
                        name="db",
                        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=AsyncSession,
                        default=Depends(get_db),
                    ),
                )

            # Sort parameters: non-default values must come before default values
            new_params.sort(
                key=lambda p: (
                    p.kind.value,
                    p.default is not inspect.Parameter.empty,
                )
            )
            cast(Any, view).__signature__ = sig.replace(parameters=new_params)

        return view

    async def dispatch(self, **kwargs: Any) -> Response:
        """
        Route the request to the appropriate handler method.
        """
        method = self.request.method.lower()
        handler = (
            getattr(self, method, self.http_method_not_allowed)
            if method in self.http_method_names
            else self.http_method_not_allowed
        )

        if inspect.iscoroutinefunction(handler):
            return await handler(**kwargs)

        return handler(**kwargs)

    def http_method_not_allowed(self, **kwargs: Any) -> Response:
        """
        Return a 405 Method Not Allowed response.
        """
        return PlainTextResponse("Method Not Allowed", status_code=405)
