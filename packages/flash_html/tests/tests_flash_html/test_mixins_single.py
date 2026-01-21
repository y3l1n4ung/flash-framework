# test_mixins_single.py - TEST SUITE FOR SingleObjectMixin
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from fastapi import HTTPException

from flash_db.models import Model
from flash_html.views.mixins.single import SingleObjectMixin


class Product(Model):
    __tablename__ = "test_products"
    name: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(unique=True)
    published: Mapped[bool] = mapped_column(default=True)


class Blog(Model):
    __tablename__ = "test_blogs"
    title: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="draft")


@pytest_asyncio.fixture
async def product(db_session: AsyncSession):
    obj = Product(name="Laptop", slug="laptop")
    db_session.add(obj)
    await db_session.commit()
    await db_session.refresh(obj)
    return obj


@pytest_asyncio.fixture
async def unpublished_product(db_session: AsyncSession):
    obj = Product(name="Tablet", slug="tablet", published=False)
    db_session.add(obj)
    await db_session.commit()
    await db_session.refresh(obj)
    return obj


@pytest_asyncio.fixture
async def article(db_session: AsyncSession):
    obj = Blog(title="Django Tips", slug="django-tips", status="published")
    db_session.add(obj)
    await db_session.commit()
    await db_session.refresh(obj)
    return obj


@pytest.fixture
def base_mixin(db_session: AsyncSession):
    """Base mixin with db already assigned."""

    class BaseMixin(SingleObjectMixin):
        db = db_session

    return BaseMixin


class TestGetQueryset:
    """Tests for get_queryset() method."""

    def test_returns_model_queryset(self):
        """get_queryset returns model.objects.all() when only model is set."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product

        mixin = ProductDetail()
        qs = mixin.get_queryset()
        assert qs is not None
        assert hasattr(qs, "filter")

    def test_returns_custom_queryset_if_set(self):
        """get_queryset returns custom queryset if class has queryset attribute."""
        custom_qs = Product.objects.filter(Product.published == True)

        class ProductDetail(SingleObjectMixin[Product]):
            queryset = custom_qs

        mixin = ProductDetail()
        qs = mixin.get_queryset()
        assert qs is custom_qs

    def test_queryset_takes_precedence_over_model(self):
        """When both queryset and model are set, queryset is used."""
        custom_qs = Product.objects.filter(Product.published == True)

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product
            queryset = custom_qs

        mixin = ProductDetail()
        qs = mixin.get_queryset()
        assert qs is custom_qs

    def test_raises_error_when_model_and_queryset_missing(self):
        """Raises RuntimeError if neither model nor queryset is defined."""

        class BrokenDetail(SingleObjectMixin[Product]):
            pass

        mixin = BrokenDetail()
        with pytest.raises(
            RuntimeError, match="requires a .model or .queryset attribute"
        ):
            mixin.get_queryset()


class TestGetObject:
    """Tests for get_object() method."""

    @pytest.mark.asyncio
    async def test_fetch_by_pk(self, base_mixin, product):
        """Retrieves object by primary key from URL kwargs."""

        class ProductDetail(base_mixin):
            model = Product
            kwargs = {"pk": product.id}

        mixin = ProductDetail()
        obj = await mixin.get_object()

        assert obj.id == product.id
        assert obj.name == "Laptop"

    @pytest.mark.asyncio
    async def test_fetch_by_slug(self, base_mixin, product):
        """Retrieves object by slug from URL kwargs."""

        class ProductDetail(base_mixin):
            model = Product
            kwargs = {"slug": "laptop"}

        mixin = ProductDetail()
        obj = await mixin.get_object()

        assert obj.slug == "laptop"
        assert obj.name == "Laptop"

    @pytest.mark.asyncio
    async def test_custom_slug_field(self, base_mixin, article):
        """Uses custom slug_field when specified."""

        class ArticleDetail(base_mixin):
            model = Blog
            slug_field = "title"
            kwargs = {"slug": "Django Tips"}

        mixin = ArticleDetail()
        obj = await mixin.get_object()

        assert obj.title == "Django Tips"

    @pytest.mark.asyncio
    async def test_custom_pk_url_kwarg(self, base_mixin, product):
        """Respects custom pk_url_kwarg parameter name."""

        class ProductDetail(base_mixin):
            model = Product
            pk_url_kwarg = "product_id"
            kwargs = {"product_id": product.id}

        mixin = ProductDetail()
        obj = await mixin.get_object()

        assert obj.id == product.id

    @pytest.mark.asyncio
    async def test_custom_slug_url_kwarg(self, base_mixin, product):
        """Respects custom slug_url_kwarg parameter name."""

        class ProductDetail(base_mixin):
            model = Product
            slug_url_kwarg = "product_slug"
            kwargs = {"product_slug": "laptop"}

        mixin = ProductDetail()
        obj = await mixin.get_object()

        assert obj.slug == "laptop"

    @pytest.mark.asyncio
    async def test_returns_404_when_not_found(self, base_mixin):
        """Raises HTTPException with 404 status when object doesn't exist."""

        class ProductDetail(base_mixin):
            model = Product
            kwargs = {"pk": 9999}

        mixin = ProductDetail()

        with pytest.raises(HTTPException) as exc:
            await mixin.get_object()

        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_error_when_url_params_missing(self, base_mixin):
        """Raises AttributeError if neither pk nor slug in kwargs."""

        class ProductDetail(base_mixin):
            model = Product
            kwargs = {}

        mixin = ProductDetail()

        with pytest.raises(AttributeError, match="URL missing"):
            await mixin.get_object()

    @pytest.mark.asyncio
    async def test_raises_error_when_slug_field_missing(self, base_mixin):
        """Raises AttributeError if model doesn't have the specified slug_field."""

        class ProductDetail(base_mixin):
            model = Product
            slug_field = "invalid_field"
            kwargs = {"slug": "test"}

        mixin = ProductDetail()

        with pytest.raises(AttributeError, match="lacks 'invalid_field'"):
            await mixin.get_object()

    @pytest.mark.asyncio
    async def test_accepts_custom_queryset_parameter(
        self, base_mixin, unpublished_product
    ):
        """get_object accepts queryset parameter to override default."""

        class ProductDetail(base_mixin):
            model = Product
            kwargs = {"pk": unpublished_product.id}

        mixin = ProductDetail()

        published_qs = Product.objects.filter(Product.published == True)
        with pytest.raises(HTTPException):
            await mixin.get_object(queryset=published_qs)

        obj = await mixin.get_object()
        assert obj.id == unpublished_product.id

    @pytest.mark.asyncio
    async def test_model_from_queryset_when_not_set(self, base_mixin, product):
        """Infers model from queryset when model is not explicitly set."""

        class ProductDetail(base_mixin):
            queryset = Product.objects.all()
            kwargs = {"pk": product.id}

        mixin = ProductDetail()
        obj = await mixin.get_object()

        assert obj.id == product.id


class TestGetContextObjectName:
    """Tests for get_context_object_name() method."""

    def test_returns_lowercase_model_name(self, product):
        """Returns lowercase model class name by default."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product

        mixin = ProductDetail()
        name = mixin.get_context_object_name(product)

        assert name == "product"

    def test_returns_custom_name_when_set(self, product):
        """Returns custom context_object_name when specified."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product
            context_object_name = "item"

        mixin = ProductDetail()
        name = mixin.get_context_object_name(product)

        assert name == "item"

    def test_custom_name_overrides_default(self, article):
        """Custom context_object_name takes precedence."""

        class ArticleDetail(SingleObjectMixin[Blog]):
            model = Blog
            context_object_name = "post"

        mixin = ArticleDetail()
        name = mixin.get_context_object_name(article)

        assert name == "post"


class TestGetContextData:
    """Tests for get_context_data() method."""

    def test_includes_object_and_lowercase_name(self, product):
        """Context includes 'object' and lowercase model name."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product
            object = product

        mixin = ProductDetail()
        ctx = mixin.get_context_data()

        assert ctx["object"] == product
        assert ctx["product"] == product

    def test_skips_object_when_none(self):
        """Object and its name are not in context when object is None."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product
            object = None

        mixin = ProductDetail()
        ctx = mixin.get_context_data()

        assert "object" not in ctx
        assert "product" not in ctx

    def test_uses_custom_context_name(self, product):
        """Uses custom context_object_name in context instead of default."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product
            context_object_name = "item"
            object = product

        mixin = ProductDetail()
        ctx = mixin.get_context_data()

        assert ctx["object"] == product
        assert ctx["item"] == product
        assert "product" not in ctx

    def test_merges_kwargs_into_context(self, product):
        """Keyword arguments are merged into returned context."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product
            object = product

        mixin = ProductDetail()
        ctx = mixin.get_context_data(sidebar=True, user="Alice")

        assert ctx["sidebar"] is True
        assert ctx["user"] == "Alice"
        assert ctx["object"] == product

    def test_calls_parent_get_context_data(self, product):
        """Calls super().get_context_data() to include ContextMixin behavior."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product
            object = product
            extra_context = {"site": "MyShop"}

        mixin = ProductDetail()
        ctx = mixin.get_context_data()

        assert "view" in ctx
        assert ctx["view"] is mixin
        assert ctx["site"] == "MyShop"


class TestIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_fetch_and_build_context(self, base_mixin, product):
        """Full workflow: fetch object and build context."""

        class ProductDetail(base_mixin):
            model = Product
            kwargs = {"pk": product.id}

        mixin = ProductDetail()

        mixin.object = await mixin.get_object()
        ctx = mixin.get_context_data(page="products")

        assert ctx["object"] == product
        assert ctx["product"] == product
        assert ctx["page"] == "products"

    @pytest.mark.asyncio
    async def test_fetch_by_slug_and_context(self, base_mixin, article):
        """Fetch by slug and include in context."""

        class ArticleDetail(base_mixin):
            model = Blog
            slug_field = "slug"
            context_object_name = "post"
            kwargs = {"slug": "django-tips"}

        mixin = ArticleDetail()

        mixin.object = await mixin.get_object()
        ctx = mixin.get_context_data()

        assert ctx["object"] == article
        assert ctx["post"] == article
        assert ctx["object"].title == "Django Tips"

    @pytest.mark.asyncio
    async def test_filter_with_custom_queryset(self, base_mixin, unpublished_product):
        """Subclass can override get_queryset to filter results."""

        class PublishedProductDetail(base_mixin):
            model = Product
            kwargs = {"pk": unpublished_product.id}

            def get_queryset(self):
                return self.model.objects.filter(Product.published.is_(True))

        mixin = PublishedProductDetail()

        with pytest.raises(HTTPException) as exc:
            await mixin.get_object()

        assert exc.value.status_code == 404
