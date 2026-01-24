from typing import Any, Generic, TypeVar

from fastapi import Response
from flash_db.models import Model

from ..generic import TemplateView
from ..mixins import SingleObjectMixin

T = TypeVar("T", bound=Model)


class DetailView(SingleObjectMixin[T], TemplateView, Generic[T]):
    """
    Render a "detail" view of an object.

    By default, this view will fetch the object based on a 'pk' or 'slug'
    passed in the URL kwargs, inject it into the context, and render
    the template.

    Attributes:
        model (type[T]): (Required) The FlashDB Model class to query.
        template_name (str): (Required) The name of the template to render.
        queryset (QuerySet[T] | None): (Optional) Specific QuerySet to use.
        context_object_name (str | None): (Optional) The name to use for the
            object in the template context.
        slug_field (str): (Optional) Model field name for slug lookup.
        pk_url_kwarg (str): (Optional) URL param name for primary key.
        slug_url_kwarg (str): (Optional) URL param name for slug.

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

    async def get(self, **kwargs: Any) -> Response:
        """
        Handle GET requests: fetch the object and render the template.

        Args:
            request: The current FastAPI request.
            **kwargs: Arbitrary keyword arguments

        Returns:
            Response: The rendered HTML response containing the object context.
        """
        self.object = await self.get_object()
        return await super().get(**kwargs)
