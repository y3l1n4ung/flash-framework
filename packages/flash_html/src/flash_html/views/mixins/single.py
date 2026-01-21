from typing import Any, Generic, TypeVar, cast

from fastapi import Depends, HTTPException, Request
from flash_db.db import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from flash_db.models import Model
from flash_db.queryset import QuerySet
from flash_html.views.mixins.context import ContextMixin

T = TypeVar("T", bound=Model)


class SingleObjectMixin(ContextMixin, Generic[T]):
    """
    Retrieve a single object from the database.

    Integrates with `ContextMixin` to inject the object into the template context.
    The database session `db` must be assigned to the instance before calling
    `get_object`.

    Attributes:
        model: The FlashDB Model class to query.
        queryset: Specific QuerySet to use (optional).
        db: The SQLAlchemy async session instance.
        object: The fetched model instance (T | None).
        slug_field: Model field name for slug lookup (default "slug").
        pk_url_kwarg: URL param name for primary key (default "pk").
        slug_url_kwarg: URL param name for slug (default "slug").

    Example:
        >>> class ArticleDetail(SingleObjectMixin[Article], TemplateView):
        ...     model = Article
        ...     template_name = "detail.html"
        ...     db: AsyncSession = Depends(get_db)
        ...
        ...     async def get(self, request):
        ...         return await super().get(request)

        >>> class PostDetail(SingleObjectMixin[Post], TemplateView):
        ...     model = Post
        ...     slug_field = "alias"
        ...     slug_url_kwarg = "post_alias"
        ...     db: AsyncSession = Depends(get_db)
        ...
        ...     async def get(self, request):
        ...         return await super().get(request)

        >>> from fastapi import FastAPI, Depends
        >>> from flash_db.models import Model
        >>> from flash_html.views.generic.detail import DetailView
        >>>
        >>> class Product(Model):
        ...     name: Mapped[str] = mapped_column()
        ...
        >>> class ProductDetail(DetailView[Product]):
        ...     model = Product
        ...     template_name = "product.html"
        ...     context_object_name = "item"
        ...     db: AsyncSession = Depends(get_db)
        ...
        ...     async def get(self, request):
        ...         return await super().get(request)
        ...
        >>> app = FastAPI()
        >>> app.add_api_route("/products/{pk}", ProductDetail.as_view())
    """

    model: type[T] | None = None
    queryset: QuerySet[T] | None = None
    db: AsyncSession = Depends(get_db)
    object: T | None = None  # Initially None, populated during request
    slug_field: str = "slug"
    context_object_name: str | None = None
    slug_url_kwarg: str = "slug"
    pk_url_kwarg: str = "pk"

    # Runtime attributes provided by the Base View
    kwargs: dict[str, Any]
    request: Request

    def get_queryset(self) -> QuerySet[T]:
        """
        Return the `QuerySet` used to look up the object.

        Returns:
            QuerySet[T]: A flash_db queryset instance.

        Raises:
            RuntimeError: If neither `model` nor `queryset` is defined.

        Example:
            >>> class ActiveUserMixin(SingleObjectMixin[User]):
            ...     model = User
            ...     def get_queryset(self):
            ...         return self.model.objects.filter(User.is_active == True)
        """
        if self.queryset is not None:
            return self.queryset

        if self.model:
            return self.model.objects.all()

        raise RuntimeError(
            f"{self.__class__.__name__} requires a .model or .queryset attribute."
        )

    async def get_object(self, queryset: QuerySet[T] | None = None) -> T:
        """
        Fetch the object based on URL parameters (pk/slug).

        Args:
            queryset: Optional queryset override.

        Returns:
            T: The fetched model instance.

        Raises:
            HTTPException: 404 if the object is not found.
            AttributeError: If self.db is not assigned.

        Example:
            >>> # Inside a View's get() method:
            >>> obj = await self.get_object()
            >>>
            >>> # Using a custom filtered queryset:
            >>> qs = self.model.objects.filter(Post.status == "published")
            >>> obj = await self.get_object(queryset=qs)
        """
        if queryset is None:
            queryset = self.get_queryset()

        model = self.model or getattr(queryset, "model", None)
        if not model:
            raise RuntimeError(f"Model class undefined for {self.__class__.__name__}.")

        pk = self.kwargs.get(self.pk_url_kwarg)
        slug = self.kwargs.get(self.slug_url_kwarg)

        # Check for mandatory DB session
        if not hasattr(self, "db"):
            raise AttributeError(
                f"{self.__class__.__name__} requires 'self.db' to be assigned "
                "before calling get_object()."
            )

        # Apply Filters
        if pk is not None:
            if not hasattr(model, "id"):
                raise AttributeError(f"Model {model.__name__} has no 'id' field.")
            queryset = queryset.filter(model.id == pk)
        elif slug is not None:
            field = getattr(model, self.slug_field, None)
            if field is None:
                raise AttributeError(
                    f"Model {model.__name__} lacks '{self.slug_field}'."
                )
            queryset = queryset.filter(field == slug)
        else:
            raise AttributeError(
                f"URL missing '{self.pk_url_kwarg}' or '{self.slug_url_kwarg}'."
            )

        # Execute
        try:
            obj = await queryset.first(self.db)
            if obj is None:
                raise HTTPException(status_code=404, detail="Object not found")
            return cast(T, obj)
        except Exception as e:
            if (
                "DoesNotExist" in e.__class__.__name__
                or "NotFound" in e.__class__.__name__
            ):
                raise HTTPException(status_code=404, detail="Object not found")
            raise e

    def get_context_object_name(self, obj: T) -> str | None:
        """
        Return the context variable name for the object.

        Returns:
            str | None: The lowercase model name or custom override.

        Example:
            >>> # Assuming obj is an instance of 'Article'
            >>> mixin.get_context_object_name(article_obj)
            'article'
        """
        if self.context_object_name:
            return self.context_object_name

        if hasattr(obj, "__class__"):
            return obj.__class__.__name__.lower()

        return None

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """
        Insert the object into the context dictionary.

        Returns:
            dict[str, Any]: Merged context data.

        Example:
            >>> # Assuming self.object is set and is an 'Article' instance
            >>> ctx = self.get_context_data(sidebar=True)
            >>> assert "object" in ctx
            >>> assert ctx["object"] == self.object
        """
        context = {}
        # Clean check instead of hasattr
        if self.object is not None:
            context["object"] = self.object
            name = self.get_context_object_name(self.object)
            if name:
                context[name] = self.object

        context.update(kwargs)
        return super().get_context_data(**context)
