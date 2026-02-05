# packages/flash_html/src/flash_html/views/mixins/template.py
from typing import Any

from fastapi import Request, Response

from flash_html.template_manager import TemplateManager


class TemplateResponseMixin:
    """
    Mixin that constructs a response using a template.

    It resolves the `TemplateManager` from `request.app.state.template_manager`
    by default, or uses an injected instance.

    Example:
        >>> class MyView(TemplateResponseMixin):
        ...     template_name = "index.html"
        ...
        >>> view = MyView()
        >>> view.get_template_names()
        ['index.html']
    """

    template_name: str | None = None
    template_engine: TemplateManager | None = None
    content_type: str | None = None
    request: Request

    def get_template_names(self) -> list[str]:
        """
        Return a list of template names to be used for the request.

        Example:
            >>> class HomeView(TemplateResponseMixin):
            ...     template_name = "home.html"
            >>> view = HomeView()
            >>> view.get_template_names()
            ['home.html']
        """
        if self.template_name is None:
            msg = (
                "TemplateResponseMixin requires either a definition of "
                "'template_name' or an implementation of 'get_template_names()'"
            )
            raise ValueError(
                msg,
            )
        return [self.template_name]

    def render_to_response(
        self,
        context: dict[str, Any],
        **response_kwargs: Any,
    ) -> Response:
        """
        Return a response, using the `template_engine` to render the template.

        This method locates the configured `TemplateManager` (either injected into the
        instance or found in `request.app.state`) and calls its `TemplateResponse`.

        Args:
            context: Dictionary of context data for the template.
            **response_kwargs: Keyword arguments passed to the
                TemplateResponse constructor.

        Returns:
            Response: The rendered HTML response.

        Raises:
            RuntimeError: If the Template engine cannot be resolved.
        """
        # 1. Resolve the engine
        # Priority: Instance attribute (injected via as_view) -> App State
        engine = self.template_engine

        if (
            not engine
            and hasattr(self, "request")
            and hasattr(self.request.app.state, "template_manager")
        ):
            engine = self.request.app.state.template_manager

        if not engine:
            msg = (
                "Template engine not found. "
                "Initialize TemplateManager and attach it to "
                "`app.state.template_manager` "
                "or pass it to view via `as_view(template_engine=...)`."
            )
            raise RuntimeError(
                msg,
            )

        # 2. Add Request to context (Required by Starlette/Jinja2Templates)
        # This allows templates to access {{ request }} and url_for()
        if not hasattr(self, "request") or self.request is None:
            msg = "Request not set on view. Ensure the view is called via as_view()."
            raise RuntimeError(msg)
        context.setdefault("request", self.request)

        # 3. Render
        template_name = self.get_template_names()[0]

        return engine.templates.TemplateResponse(
            self.request,
            name=template_name,
            context=context,
            media_type=self.content_type,
            **response_kwargs,
        )
