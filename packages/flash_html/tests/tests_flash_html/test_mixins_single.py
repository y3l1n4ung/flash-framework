from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from flash_html.views.mixins.single import SingleObjectMixin
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import HTMLTestProduct


@pytest_asyncio.fixture
async def product(db_session: AsyncSession):
    obj = HTMLTestProduct(name="Laptop", slug="laptop", published=True)
    db_session.add(obj)
    await db_session.commit()
    await db_session.refresh(obj)
    return obj


@pytest_asyncio.fixture
async def unpublished_product(db_session: AsyncSession):
    obj = HTMLTestProduct(name="Tablet", slug="tablet", published=False)
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

    def test_missing_model_not_enforced_for_base_classes(self):
        """Base view classes (DetailView, CreateView, etc.) don't need
        model attribute."""
        try:

            class DetailView(SingleObjectMixin):
                pass

            class CreateView(SingleObjectMixin):
                pass

            class UpdateView(SingleObjectMixin):
                pass

            class DeleteView(SingleObjectMixin):
                pass

            # If we reach here, no error was raised - which is correct
            assert True
        except TypeError:
            pytest.fail("Base view classes should not require 'model' attribute")

    def test_model_validator_failure_re_raised(self, monkeypatch):
        """If ModelValidator.validate_model() raises TypeError, it gets re-raised."""
        from flash_db.validator import ModelValidator

        def mock_validate_model(_model):
            msg = "Model validation failed: invalid model structure"
            raise TypeError(msg)

        monkeypatch.setattr(ModelValidator, "validate_model", mock_validate_model)

        with pytest.raises(TypeError) as excinfo:

            class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
                model = HTMLTestProduct

        assert "Model validation failed" in str(excinfo.value)

    def test_get_queryset_default(self):
        """Default queryset is model.objects.all()."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = HTMLTestProductDetail()
        assert mixin.get_queryset() is not None

    def test_get_queryset_returns_predefined_queryset(self):
        """
        Verify that the mixin returns self.queryset if it is set.
        """

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            # Define a specific queryset on the class level
            queryset = HTMLTestProduct.objects.filter(
                HTMLTestProduct.published.is_(True)
            )

        mixin = HTMLTestProductDetail()
        qs = mixin.get_queryset()

        assert qs == HTMLTestProductDetail.queryset
        assert "published" in str(qs._stmt)

    def test_model_validation_called_on_subclass(self):
        """Model validator is invoked during subclass creation."""

        class ValidHTMLTestProductView(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        # If we reach here, the model passed validation
        assert ValidHTMLTestProductView.model == HTMLTestProduct


class TestGetObject:
    """Tests for the get_object() method and 404 logic."""

    @pytest.mark.asyncio
    async def test_fetch_by_pk_success(self, setup_mixin, product):
        """Successfully fetch object by primary key."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductDetail, pk=product.id)
        obj = await mixin.get_object()
        assert obj.id == product.id

    @pytest.mark.asyncio
    async def test_fetch_by_slug_success(self, setup_mixin, product):
        """Successfully fetch object by slug."""
        assert product is not None

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductDetail, slug="laptop")
        obj = await mixin.get_object()
        assert obj.slug == "laptop"

    @pytest.mark.asyncio
    async def test_auto_error_404(self, setup_mixin):
        """Raise 404 if object not found and auto_error is True."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductDetail, pk=999)

        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_object(auto_error=True)
        assert excinfo.value.status_code == 404

    @pytest.mark.asyncio
    async def test_auto_error_disabled(self, setup_mixin):
        """Return None if object not found and auto_error is False."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductDetail, pk=999)
        obj = await mixin.get_object(auto_error=False)
        assert obj is None

    @pytest.mark.asyncio
    async def test_custom_queryset_filtering(self, setup_mixin, unpublished_product):
        """Overridden get_queryset is respected."""

        class PublishedDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

            def get_queryset(self):
                return self.model.objects.filter(HTMLTestProduct.published.is_(True))

        mixin = setup_mixin(PublishedDetail, pk=unpublished_product.id)

        # Should 404 because the product is unpublished
        with pytest.raises(HTTPException):
            await mixin.get_object()

    @pytest.mark.asyncio
    async def test_raises_runtime_error_without_db(self):
        """Clear error if the DB session was never injected."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = HTMLTestProductDetail()
        mixin.kwargs = {"pk": 1}

        with pytest.raises(
            RuntimeError,
            match="Database session is required but not set",
        ):
            await mixin.get_object()

    @pytest.mark.asyncio
    async def test_pk_takes_priority_over_slug(self, setup_mixin, product):
        """If both PK and Slug are provided, PK is used for the lookup."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        # Provide correct PK but a completely wrong slug
        mixin = setup_mixin(
            HTMLTestProductDetail, pk=product.id, slug="wrong-slug-here"
        )

        # This should still succeed because it looks up by PK first
        obj = await mixin.get_object()
        assert obj.id == product.id

    @pytest.mark.asyncio
    async def test_invalid_slug_field_configuration(self, setup_mixin):
        """Raise AttributeError if slug_field does not exist on the model."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            slug_field = "non_existent_column"

        mixin = setup_mixin(HTMLTestProductDetail, slug="some-slug")

        with pytest.raises(AttributeError, match="has no field 'non_existent_column'"):
            await mixin.get_object()

    @pytest.mark.asyncio
    async def test_ambiguous_lookup_fails(self, setup_mixin):
        """Raise error if URL kwargs contain neither pk nor slug."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        # URL only has 'category_id', which the mixin doesn't know how to use
        mixin = setup_mixin(HTMLTestProductDetail, category_id=5)

        with pytest.raises(AttributeError, match="URL must include 'pk' or 'slug'"):
            await mixin.get_object()


class TestErrorHandling:
    """Tests for database error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_database_not_found_returns_none_when_auto_error_false(
        self,
        setup_mixin,
    ):
        """When auto_error=False, None is returned instead of raising 404."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductDetail, pk=9999)
        result = await mixin.get_object(auto_error=False)
        assert result is None

    @pytest.mark.asyncio
    async def test_404_exception_has_correct_detail_message(self, setup_mixin):
        """404 exception includes model name in detail message."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductDetail, pk=9999)

        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_object(auto_error=True)

        assert "HTMLTestProduct not found" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_custom_slug_url_kwarg(self, setup_mixin, product):
        """Mixin respects custom slug_url_kwarg configuration."""
        assert product is not None

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            slug_url_kwarg = "product_slug"

        mixin = setup_mixin(HTMLTestProductDetail, product_slug="laptop")
        obj = await mixin.get_object()
        assert obj.slug == "laptop"

    @pytest.mark.asyncio
    async def test_custom_pk_url_kwarg(self, setup_mixin, product):
        """Mixin respects custom pk_url_kwarg configuration."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            pk_url_kwarg = "product_id"

        mixin = setup_mixin(HTMLTestProductDetail, product_id=product.id)
        obj = await mixin.get_object()
        assert obj.id == product.id

    @pytest.mark.asyncio
    async def test_get_object_with_custom_queryset_override(self, setup_mixin, product):
        """Passed queryset parameter overrides get_queryset() method."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductDetail, pk=product.id)
        custom_qs = HTMLTestProduct.objects.filter(HTMLTestProduct.published.is_(True))

        obj = await mixin.get_object(queryset=custom_qs)
        assert obj.id == product.id

    def test_get_model_fields_returns_field_names(self):
        """_get_model_fields() returns list of column names."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = HTMLTestProductDetail()
        fields = mixin._get_model_fields()

        # Should include expected fields
        assert isinstance(fields, list)
        assert len(fields) > 0
        # HTMLTestProduct typically has: id, name, slug, published
        assert "id" in fields or "name" in fields or "slug" in fields

    def test_get_model_fields_handles_error_gracefully(self):
        """_get_model_fields() handles errors and returns fallback."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = HTMLTestProductDetail()
        original_table = mixin.model.__table__
        try:
            mixin.model.__table__ = None  # type: ignore
            fields = mixin._get_model_fields()
            # Should return fallback when error occurs
            assert fields == ["<unable to fetch fields>"]
        finally:
            mixin.model.__table__ = original_table


class TestContextObjectName:
    """Tests for context_object_name attribute."""

    def test_context_object_name_default_none(self):
        """context_object_name defaults to None."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = HTMLTestProductDetail()
        assert mixin.context_object_name is None

    def test_context_object_name_can_be_set(self):
        """context_object_name can be customized."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            context_object_name = "htmltestproduct"

        mixin = HTMLTestProductDetail()
        assert mixin.context_object_name == "htmltestproduct"


class TestDatabaseExceptions:
    """Tests for database error handling in SingleObjectMixin."""

    @pytest.fixture
    def mock_queryset(self):
        """Creates a mock queryset that can be configured per test."""
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        return mock_qs

    @pytest.fixture
    def mixin(self, db_session, mock_queryset):
        """Returns a HTMLTestProductDetail instance with a mocked get_queryset."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

            def get_queryset(self):
                return mock_queryset

        instance = HTMLTestProductDetail()
        instance.db = db_session
        instance.kwargs = {"pk": 1}
        return instance

    @pytest.mark.asyncio
    async def test_operational_error_returns_503(self, mixin, mock_queryset):
        mock_queryset.first = AsyncMock(
            side_effect=OperationalError(
                "Lost",
                None,
                Exception("OP ERROR"),
            ),
        )

        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_object()

        assert excinfo.value.status_code == 503
        assert "temporarily unavailable" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_integrity_error_returns_500(self, mixin, mock_queryset):
        mock_queryset.first = AsyncMock(
            side_effect=IntegrityError(
                "Conflict",
                None,
                Exception("ERROR"),
            ),
        )

        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_object()

        assert excinfo.value.status_code == 500
        assert "Internal database error occurred." in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_database_error_returns_500(self, mixin, mock_queryset):
        mock_queryset.first = AsyncMock(
            side_effect=DatabaseError(
                "Error",
                None,
                Exception("ERROR"),
            ),
        )

        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_object()

        assert excinfo.value.status_code == 500
        assert "Internal database error occurred." in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_500(self, mixin, mock_queryset):
        mock_queryset.first = AsyncMock(side_effect=ValueError("Unexpected"))

        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_object()

        assert excinfo.value.status_code == 500
        assert "Internal server error" in excinfo.value.detail

    @pytest.mark.asyncio
    @pytest.mark.parametrize("exception_class", [AttributeError, TypeError])
    async def test_passthrough_exceptions(self, mixin, mock_queryset, exception_class):
        """AttributeError and TypeError should not be swallowed/converted."""
        mock_queryset.first = AsyncMock(side_effect=exception_class("Reraise me"))

        with pytest.raises(exception_class, match="Reraise me"):
            await mixin.get_object()


class TestSlugFieldConfiguration:
    """Tests for slug_field configuration and behavior."""

    @pytest.mark.asyncio
    async def test_custom_slug_field(self, setup_mixin, product):
        """Mixin uses custom slug_field when configured."""
        assert product is not None

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            slug_field = "slug"

        mixin = setup_mixin(HTMLTestProductDetail, slug="laptop")
        obj = await mixin.get_object()
        assert obj.slug == "laptop"

    @pytest.mark.asyncio
    async def test_slug_field_not_found_shows_available_fields(self, setup_mixin):
        """AttributeError message includes available fields when slug_field
        doesn't exist."""

        class HTMLTestProductDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            slug_field = "invalid_field"

        mixin = setup_mixin(HTMLTestProductDetail, slug="test")

        with pytest.raises(AttributeError) as excinfo:
            await mixin.get_object()

        error_msg = str(excinfo.value)
        assert "invalid_field" in error_msg


class TestQuerysetOverrides:
    """Tests for queryset overriding and filtering."""

    @pytest.mark.asyncio
    async def test_queryset_class_attribute_overrides_default(
        self,
        setup_mixin,
        product,
        unpublished_product,
    ):
        """Class-level queryset attribute filters results."""

        class OnlyPublishedDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            queryset = HTMLTestProduct.objects.filter(
                HTMLTestProduct.published.is_(True)
            )

        # Should find published product
        mixin = setup_mixin(OnlyPublishedDetail, pk=product.id)
        obj = await mixin.get_object()
        assert obj.id == product.id

        # Should NOT find unpublished product
        mixin = setup_mixin(OnlyPublishedDetail, pk=unpublished_product.id)
        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_object()
        assert excinfo.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_queryset_override_adds_filters(
        self,
        setup_mixin,
        product,
        unpublished_product,
    ):
        """Overriding get_queryset() allows dynamic filtering."""

        class PublishedOnlyDetail(SingleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

            def get_queryset(self):
                return self.model.objects.filter(HTMLTestProduct.published.is_(True))

        # Published product found
        mixin = setup_mixin(PublishedOnlyDetail, pk=product.id)
        obj = await mixin.get_object()
        assert obj.published is True

        # Unpublished product not found
        mixin = setup_mixin(PublishedOnlyDetail, pk=unpublished_product.id)
        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_object()
        assert excinfo.value.status_code == 404
