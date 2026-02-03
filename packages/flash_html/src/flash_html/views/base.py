import inspect
from typing import Any, Callable, ClassVar, Coroutine, cast

from fastapi import Depends, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse
from flash_authorization.dependencies import PermissionRedirectError
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

    def __init__(self, *_arg: Any, **kwargs: Any) -> None:
        """
        Initialize the view instance with configuration overrides.
        """
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def as_view(
        cls,
        method: str | None = None,
        **initkwargs: Any,
    ) -> Callable[..., Coroutine[Any, Any, Response]]:
        """
        Create a FastAPI-compatible endpoint callable.

        This method validates attributes and reconstructs the function signature
        to support FastAPI's dependency injection system.

        Args:
            method: Optional HTTP method name used to build the FastAPI signature
                from a specific handler (e.g., "post"). If omitted, the first
                available handler is used.
            **initkwargs: Attributes to override on the view instance.

        Returns:
            Callable: An async function used as the FastAPI route handler.
        """
        # 1. Validate initkwargs against class attributes
        for key in initkwargs:
            if not hasattr(cls, key):
                msg = (
                    f"{cls.__name__}() received an invalid keyword {key!r}. "
                    f"as_view() only accepts arguments that are already attributes "
                    f"of the class."
                )
                raise TypeError(
                    msg,
                )

        method_name = method.lower() if method else None

        if method_name and method_name not in cls.http_method_names:
            msg = (
                f"{cls.__name__}() received an invalid method {method!r}. "
                "Use one of: " + ", ".join(cls.http_method_names)
            )
            raise ValueError(msg)

        handler = None
        if method_name:
            handler = getattr(cls, method_name, None)
            if handler is None or handler.__name__ == "http_method_not_allowed":
                msg = (
                    f"{cls.__name__} has no '{method_name}' handler. "
                    "Define it or remove the method override."
                )
                raise ValueError(msg)
        else:
            for candidate_name in cls.http_method_names:
                if hasattr(cls, candidate_name):
                    potential_handler = getattr(cls, candidate_name)
                    if potential_handler.__name__ != "http_method_not_allowed":
                        handler = potential_handler
                        break

        handler_param_names: set[str] = set()

        async def view(request: Request, *_arg, **kwargs: Any) -> Response:
            self = cls(**initkwargs)
            self.request = request

            # Extract database session if provided by FastAPI injection
            if "db" in kwargs:
                self.db = kwargs["db"]  # type: ignore
                if "db" not in handler_param_names:
                    kwargs.pop("db")

            # Merge path parameters and additional kwargs
            self.kwargs = {
                **request.path_params,
                **{key: value for key, value in kwargs.items() if key != "db"},
            }

            call_kwargs = dict(kwargs)
            if "request" in handler_param_names:
                call_kwargs["request"] = request

            return await self.dispatch(**call_kwargs)

        view.__doc__ = cls.__doc__
        view.__module__ = cls.__module__
        view.__name__ = f"{cls.__name__}_{method_name}" if method_name else cls.__name__

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
            handler_param_names = set(param_names)

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
            cls.resolve_dependencies(new_params, **initkwargs)

            # Auto-inject DB session if the view defines a 'model' (DB-bound views)
            # TODO: move to resolve dependencies
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
                ),
            )
            cast("Any", view).__signature__ = sig.replace(parameters=new_params)

        return view

    @classmethod
    def resolve_dependencies(
        cls, params: list[inspect.Parameter], **kwargs: Any
    ) -> None:
        """
        Hook to inject additional dependencies into the view signature.
        Accepts **kwargs (the arguments passed to as_view)
        to allow dynamic configuration.
        """

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

        try:
            if inspect.iscoroutinefunction(handler):
                return await handler(**kwargs)

            return handler(**kwargs)
        except PermissionRedirectError as e:
            return RedirectResponse(e.url, status_code=302)
        except Exception:
            raise

    def http_method_not_allowed(self, **_kwargs: Any) -> Response:
        """
        Return a 405 Method Not Allowed response.
        """
        return PlainTextResponse("Method Not Allowed", status_code=405)
