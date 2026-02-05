from typing import Any, Generic, TypeVar

from fastapi import Response
from flash_db.models import Model

from flash_html.views.mixins import PermissionMixin, SingleObjectMixin

from .base import TemplateView

T = TypeVar("T", bound=Model)


class DetailView(SingleObjectMixin[T], PermissionMixin, TemplateView, Generic[T]):
    """
    Render a "detail" view of an object.

    By default, this view will fetch the object based on a 'pk' or 'slug'
    passed in the URL kwargs, inject it into the context, and render
    the template.

    Example:
        >>> # 1. Define a detail view class
        >>> class ProductDetail(DetailView[Product]):
        ...     model = Product
        ...     template_name = "product.html"
        ...     context_object_name = "item"
        ...
        >>> # 2. Configure via as_view()
        >>> app.add_api_route("/products/{pk}", ProductDetail.as_view())
    """

    async def get(self, *args, **kwargs: Any) -> Response:
        """
        Handle GET requests: fetch the object and render the template.

        Args:
            request: The current FastAPI request.
            **kwargs: Arbitrary keyword arguments

        Returns:
            Response: The rendered HTML response containing the object context.
        """

        self.object = await self.get_object()
        await self.check_object_permissions(self.object)
        return await super().get(*args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        name = self.context_object_name or self.model.__name__.lower()
        context[name] = self.object
        return context
