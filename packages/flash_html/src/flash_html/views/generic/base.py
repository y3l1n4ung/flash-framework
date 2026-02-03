from typing import Any

from fastapi import Response

from flash_html.views.base import View
from flash_html.views.mixins import ContextMixin, TemplateResponseMixin


class TemplateView(TemplateResponseMixin, ContextMixin, View):
    """
    Render a template.

    This view handles GET requests by fetching context data and rendering
    the specified template.

    Attributes:
        template_name (str): The name of the template to render.

    Example:
        >>> # 1. Define a view class
        >>> class HomeView(TemplateView):
        ...     template_name = "home.html"
        ...
        >>> # 2. configure via as_view()
        >>> app.add_api_route("/", HomeView.as_view(template_name="index.html"))
    """

    async def get(self, *args: Any, **kwargs: Any) -> Response:  # noqa: ARG002
        """
        Handle GET requests: render the template with context.

        Args:
            request: The current FastAPI request.
            *args:
            **kwargs: Arbitrary keyword arguments

        Returns:
            Response: The rendered HTML response.
        """
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)
