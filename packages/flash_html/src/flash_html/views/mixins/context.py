from typing import Any, Generic, TypeVar

from pydantic import BaseModel

# Type variable bound to Pydantic Models or Dicts.
# This allows subclasses to define strict types for their context.
ExtraContextT = TypeVar("ExtraContextT", bound=BaseModel | dict[str, Any])


class ContextMixin(Generic[ExtraContextT]):
    """
    Provide context data for template rendering.

    This mixin standardizes how data is passed to the template engine.
    It supports merging `extra_context` into the final context dictionary.

    Type Safety:
        This class is Generic. You can specify the Pydantic model used for
        context to get IDE support.

    Example:
        class PageData(BaseModel):
            title: str

        class MyView(ContextMixin[PageData]):
            extra_context = PageData(title="Home")
    """

    extra_context: ExtraContextT | None = None

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """
        Build the template context dictionary.

        This method combines keyword arguments, the view instance, and any
        defined `extra_context` into a single dictionary for Jinja2.

        Args:
            **kwargs: Additional context variables to include. These override
                defaults but are overridden by `extra_context`.

        Returns:
            dict[str, Any]: The final context dictionary ready for rendering.

        Example:
            >>> from pydantic import BaseModel
            >>> class PageData(BaseModel):
            ...     title: str
            ...     active_tab: str
            ...
            >>> class MyView(ContextMixin[PageData]):
            ...     extra_context = PageData(title="Home", active_tab="index")
            ...
            >>> view = MyView()
            >>> ctx = view.get_context_data(user="Alice")
            >>> assert ctx["title"] == "Home"
            >>> assert ctx["user"] == "Alice"
            >>> assert "view" in ctx
        """
        context = dict(kwargs)

        context.setdefault("view", self)

        if self.extra_context is not None:
            if isinstance(self.extra_context, BaseModel):
                context.update(self.extra_context.model_dump())
            elif isinstance(self.extra_context, dict):
                context.update(self.extra_context)
            else:
                msg = (
                    f"'extra_context' must be a dict or Pydantic BaseModel, "
                    f"received {type(self.extra_context).__name__!r}."
                )
                raise TypeError(
                    msg,
                )

        return context
