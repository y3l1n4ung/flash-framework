import pytest
import pytest_asyncio
from fastapi import HTTPException
from flash_html.views.mixins.single import SingleObjectMixin
from models import Product
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def product(db_session: AsyncSession):
    obj = Product(name="Laptop", slug="laptop", published=True)
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


@pytest.fixture
def setup_mixin(db_session: AsyncSession):
    """
    Helper to configure a mixin instance with the DB session.
    This avoids the TypeError from __init_subclass__.
    """

    def _setup(mixin_cls, **kwargs):
        instance = mixin_cls()
        instance.db = db_session
        instance.kwargs = kwargs
        return instance

    return _setup


class TestSingleObjectMixinCore:
    """Tests for core initialization and queryset logic."""

    def test_missing_model_raises_type_error(self):
        """Defining a subclass without a model attribute raises TypeError."""
        with pytest.raises(TypeError) as excinfo:

            class InvalidView(SingleObjectMixin):
                pass

        assert "missing the required 'model' attribute" in str(excinfo.value)

    def test_get_queryset_default(self):
        """Default queryset is model.objects.all()."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product

        mixin = ProductDetail()
        assert mixin.get_queryset() is not None


class TestGetObject:
    """Tests for the get_object() method and 404 logic."""

    @pytest.mark.asyncio
    async def test_fetch_by_pk_success(self, setup_mixin, product):
        class ProductDetail(SingleObjectMixin[Product]):
            model = Product

        mixin = setup_mixin(ProductDetail, pk=product.id)
        obj = await mixin.get_object()
        assert obj.id == product.id

    @pytest.mark.asyncio
    async def test_fetch_by_slug_success(self, setup_mixin, product):
        class ProductDetail(SingleObjectMixin[Product]):
            model = Product

        mixin = setup_mixin(ProductDetail, slug="laptop")
        obj = await mixin.get_object()
        assert obj.slug == "laptop"

    @pytest.mark.asyncio
    async def test_auto_error_404(self, setup_mixin):
        """Raise 404 if object not found and auto_error is True."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product

        mixin = setup_mixin(ProductDetail, pk=999)

        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_object(auto_error=True)
        assert excinfo.value.status_code == 404

    @pytest.mark.asyncio
    async def test_auto_error_disabled(self, setup_mixin):
        """Return None if object not found and auto_error is False."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product

        mixin = setup_mixin(ProductDetail, pk=999)
        obj = await mixin.get_object(auto_error=False)
        assert obj is None

    @pytest.mark.asyncio
    async def test_custom_queryset_filtering(self, setup_mixin, unpublished_product):
        """Overridden get_queryset is respected."""

        class PublishedDetail(SingleObjectMixin[Product]):
            model = Product

            def get_queryset(self):
                return self.model.objects.filter(Product.published.is_(True))

        mixin = setup_mixin(PublishedDetail, pk=unpublished_product.id)

        # Should 404 because the product is unpublished
        with pytest.raises(HTTPException):
            await mixin.get_object()


class TestContextData:
    """Tests for context dictionary generation."""

    def test_context_object_naming(self, product):
        class ProductDetail(SingleObjectMixin[Product]):
            model = Product

        mixin = ProductDetail()
        mixin.object = product
        ctx = mixin.get_context_data()

        assert ctx["object"] == product
        assert ctx["product"] == product

    def test_custom_context_object_name(self, product):
        class ProductDetail(SingleObjectMixin[Product]):
            model = Product
            context_object_name = "item"

        mixin = ProductDetail()
        mixin.object = product
        ctx = mixin.get_context_data()

        assert ctx["item"] == product
        assert "product" not in ctx

    def test_empty_object_context(self):
        """Context is clean if object is None."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product

        mixin = ProductDetail()
        mixin.object = None
        ctx = mixin.get_context_data()

        assert "object" not in ctx
        assert "product" not in ctx

    @pytest.mark.asyncio
    async def test_raises_runtime_error_without_db(self):
        """Clear error if the DB session was never injected."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product

        mixin = ProductDetail()
        mixin.kwargs = {"pk": 1}

        with pytest.raises(RuntimeError, match="Database session is required!"):
            await mixin.get_object()

    @pytest.mark.asyncio
    async def test_pk_takes_priority_over_slug(self, setup_mixin, product):
        """If both PK and Slug are provided, PK is used for the lookup."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product

        # Provide correct PK but a completely wrong slug
        mixin = setup_mixin(ProductDetail, pk=product.id, slug="wrong-slug-here")

        # This should still succeed because it looks up by PK first
        obj = await mixin.get_object()
        assert obj.id == product.id

    @pytest.mark.asyncio
    async def test_invalid_slug_field_configuration(self, setup_mixin):
        """Raise AttributeError if slug_field does not exist on the model."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product
            slug_field = "non_existent_column"

        mixin = setup_mixin(ProductDetail, slug="some-slug")

        with pytest.raises(AttributeError, match="lacks 'non_existent_column'"):
            await mixin.get_object()

    @pytest.mark.asyncio
    async def test_ambiguous_lookup_fails(self, setup_mixin):
        """Raise error if URL kwargs contain neither pk nor slug."""

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product

        # URL only has 'category_id', which the mixin doesn't know how to use
        mixin = setup_mixin(ProductDetail, category_id=5)

        with pytest.raises(AttributeError, match="URL missing 'pk' or 'slug'"):
            await mixin.get_object()

    def test_context_naming_acronyms(self):
        """Verify lowercase conversion for complex model names."""

        class APIKey(Product):
            pass

        class APIKeyDetail(SingleObjectMixin[APIKey]):
            model = APIKey

        mixin = APIKeyDetail()
        mixin.object = APIKey()
        ctx = mixin.get_context_data()

        assert "apikey" in ctx

    def test_get_queryset_returns_predefined_queryset(self):
        """
        Verify that the mixin returns self.queryset if it is set.
        """

        class ProductDetail(SingleObjectMixin[Product]):
            model = Product
            # Define a specific queryset on the class level
            queryset = Product.objects.filter(Product.published.is_(True))

        mixin = ProductDetail()
        qs = mixin.get_queryset()

        assert qs == ProductDetail.queryset
        assert "published" in str(qs._stmt)
