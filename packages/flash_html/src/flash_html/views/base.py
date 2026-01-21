import inspect
from typing import Any, Callable, ClassVar, Coroutine, cast

from fastapi import Request, Response
from fastapi.responses import PlainTextResponse


class View:
    """
    Async Class-Based View Root with FastAPI Dependency Injection Support.

    This class serves as the foundation for all views. It handles HTTP method
    dispatching and integrates seamlessly with FastAPI by preserving method
    signatures for dependency injection.
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

    # Instance attributes populated during request handling
    request: Request
    args: tuple[Any, ...]
    kwargs: dict[str, Any]

    def __init__(self, **kwargs: Any) -> None:
        """
        Initialize the view instance.

        Args:
            **kwargs: Instance attributes set during request handling.
                      Mapped from `as_view(**initkwargs)`.
        """
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def as_view(cls, **initkwargs: Any) -> Callable[..., Coroutine[Any, Any, Response]]:
        """
        Create a FastAPI-compatible endpoint callable.

        This method allows you to override class attributes on a per-route basis
        using `**initkwargs`. This enables reusing a single View class for multiple
        routes with different configurations.

        Strictness:
            This method validates that keys passed in `**initkwargs` must already
            exist as attributes on the class. This prevents typos.

        Args:
            **initkwargs: Attributes to override on the view instance.
                Common use cases: `template_name`, `page_title`, `paginate_by`.

        Returns:
            Callable: An async function accepting a Request and returning a Response.

        Example:
            >>> from fastapi import FastAPI, Response
            >>> app = FastAPI()
            >>>
            >>> # 1. Define a configurable view
            >>> class PageView(View):
            ...     page_title: str = "Default Title"  # Default value
            ...
            ...     async def get(self, request):
            ...         return Response(f"Title: {self.page_title}")
            >>>
            >>> # 2. Reuse for "About" page
            >>> app.add_api_route("/about", PageView.as_view(page_title="About Us"))
            >>>
            >>> # 3. Reuse for "Contact" page
            >>> app.add_api_route("/contact", PageView.as_view(page_title="Contact"))
            >>>
            >>> # 4. Error Case: Passing a non-existent attribute raises TypeError
            >>> # PageView.as_view(typo_field="Fail")  # <--- raises TypeError
        """
        # Strict Validation: Ensure passed arguments match existing class attributes.
        for key in initkwargs:
            if not hasattr(cls, key):
                raise TypeError(
                    f"{cls.__name__}() received an invalid keyword {key!r}. "
                    f"as_view() only accepts arguments that are already attributes "
                    f"of the class."
                )

        async def view(request: Request, *args: Any, **kwargs: Any) -> Response:
            # Inject the kwargs into the instance
            self = cls(**initkwargs)
            self.request = request
            self.args = args
            self.kwargs = kwargs
            return await self.dispatch(request, *args, **kwargs)

        view.__doc__ = cls.__doc__
        view.__module__ = cls.__module__
        view.__name__ = cls.__name__

        # Inspect the class to find the primary handler (e.g., 'get' or 'post').
        # This ensures that if you define dependencies in 'get(self, db: Session = Depends(get_db))',
        # FastAPI sees them in the 'view' wrapper.
        for method_name in cls.http_method_names:
            if hasattr(cls, method_name):
                handler = getattr(cls, method_name)
                # Only copy signature from actual methods, not the default 'http_method_not_allowed'
                if handler.__name__ != "http_method_not_allowed":
                    sig = inspect.signature(handler)
                    # Filter out 'self' from parameters so the wrapper matches.
                    # We keep 'request' and other params for FastAPI injection.
                    new_params = [
                        p
                        for p in sig.parameters.values()
                        if p.name != "self"
                        and p.kind != inspect.Parameter.VAR_KEYWORD
                        and p.kind != inspect.Parameter.VAR_POSITIONAL
                    ]
                    # Cast to Any to allow setting __signature__ which is dynamically typed
                    cast(Any, view).__signature__ = sig.replace(parameters=new_params)
                    break

        return view

    async def dispatch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """
        Route the request to the appropriate handler method.

        Args:
            request: The incoming FastAPI request.

        Returns:
            Response: The HTTP response generated by the handler.
        """
        method = request.method.lower()
        if method in self.http_method_names:
            handler = getattr(self, method, self.http_method_not_allowed)
        else:
            handler = self.http_method_not_allowed

        # Support both async and sync handlers
        if inspect.iscoroutinefunction(handler):
            return await handler(request, *args, **kwargs)

        # Explicitly cast to Response for strict type checkers
        return cast(Response, handler(request, *args, **kwargs))

    def http_method_not_allowed(
        self, request: Request, *args: Any, **kwargs: Any
    ) -> Response:
        """
        Handle requests for unsupported HTTP methods.

        Note: This is synchronous as it returns a static response.

        Returns:
            Response: 405 Method Not Allowed.
        """
        return PlainTextResponse("Method Not Allowed", status_code=405)
