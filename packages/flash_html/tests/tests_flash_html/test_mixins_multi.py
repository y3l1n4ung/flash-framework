import pytest
import pytest_asyncio
from fastapi import HTTPException
from flash_html.views.mixins.multi import MultipleObjectMixin
from sqlalchemy import insert
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError

from .models import HTMLTestProduct


@pytest_asyncio.fixture
async def products_data(db_session):
    """Setup test products."""
    await db_session.execute(
        insert(HTMLTestProduct).values(
            [
                {"id": 1, "name": "Laptop", "slug": "laptop-pro", "published": True},
                {"id": 2, "name": "Phone", "slug": "phone-max", "published": False},
                {"id": 3, "name": "Tablet", "slug": "tablet-pro", "published": True},
                {"id": 4, "name": "Monitor", "slug": "monitor-4k", "published": True},
                {
                    "id": 5,
                    "name": "Keyboard",
                    "slug": "keyboard-mech",
                    "published": False,
                },
            ],
        ),
    )
    await db_session.commit()


@pytest.fixture
def setup_mixin(db_session):
    """Helper to configure mixin instance with DB session."""

    def _setup(mixin_cls, **attrs):
        instance = mixin_cls()
        instance.db = db_session
        for key, value in attrs.items():
            setattr(instance, key, value)
        return instance

    return _setup


class TestMultipleObjectMixinCore:
    """Tests for core initialization and configuration."""

    def test_missing_model_raises_type_error(self):
        """Subclass without model attribute raises TypeError."""
        with pytest.raises(TypeError) as excinfo:

            class InvalidView(MultipleObjectMixin):
                pass

        assert "missing the required 'model' attribute" in str(excinfo.value)

    def test_missing_model_not_enforced_for_base_classes(self):
        """Base class ListView doesn't require model attribute."""
        try:

            class ListView(MultipleObjectMixin):
                pass

            assert True
        except TypeError:
            pytest.fail("ListView should not require 'model' attribute")

    def test_valid_subclass_with_model(self):
        """Subclass with model attribute succeeds."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        assert HTMLTestProductListView.model == HTMLTestProduct

    def test_model_validator_failure_re_raised(self, monkeypatch):
        """If ModelValidator.validate_model() raises TypeError, it gets re-raised."""
        from flash_db.validator import ModelValidator

        def mock_validate_model(_model):
            msg = "Model validation failed: invalid model structure"
            raise TypeError(msg)

        monkeypatch.setattr(ModelValidator, "validate_model", mock_validate_model)

        with pytest.raises(TypeError) as excinfo:

            class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
                model = HTMLTestProduct

        assert "Model validation failed" in str(excinfo.value)

    def test_get_queryset_default(self):
        """get_queryset() returns model.objects.all() by default."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = HTMLTestProductListView()
        qs = mixin.get_queryset()
        assert qs is not None

    def test_get_queryset_with_custom_queryset(self):
        """get_queryset() returns custom queryset if set."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            queryset = HTMLTestProduct.objects.filter(
                HTMLTestProduct.published.is_(True)
            )

        mixin = HTMLTestProductListView()
        qs = mixin.get_queryset()
        assert qs == HTMLTestProductListView.queryset


class TestResolveOrdering:
    """Tests for resolve_ordering() static method."""

    def test_resolve_ordering_empty_returns_empty_list(self):
        """Empty ordering returns empty list."""
        result = MultipleObjectMixin.resolve_ordering(None, None)
        assert result == []

    def test_resolve_ordering_single_string_asc(self):
        """Single string without prefix defaults to ascending."""
        result = MultipleObjectMixin.resolve_ordering(None, "name")
        assert result == [("name", "asc")]

    def test_resolve_ordering_single_string_desc(self):
        """Single string with '-' prefix is descending."""
        result = MultipleObjectMixin.resolve_ordering(None, "-id")
        assert result == [("id", "desc")]

    def test_resolve_ordering_multiple_strings(self):
        """Multiple ordering strings are processed."""
        result = MultipleObjectMixin.resolve_ordering(None, ["name", "-id"])
        assert result == [("name", "asc"), ("id", "desc")]

    def test_resolve_ordering_tuples_preserved(self):
        """Tuple ordering is preserved as-is."""
        result = MultipleObjectMixin.resolve_ordering(
            None,
            [("name", "desc"), ("id", "asc")],  # type: ignore
        )
        assert result == [("name", "desc"), ("id", "asc")]

    def test_resolve_ordering_params_takes_priority(self):
        """URL params ordering takes priority over class ordering."""
        result = MultipleObjectMixin.resolve_ordering([("custom_field", "asc")], "-id")
        assert result == [("custom_field", "asc")]


class TestGetObjects:
    """Tests for get_objects() method."""

    @pytest.mark.asyncio
    async def test_get_objects_success(self, setup_mixin, products_data):  # noqa: ARG002
        """Fetch objects successfully."""
        # Verify products_data fixture is available even though we create mock data

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductListView)
        data = await mixin.get_objects(limit=10, offset=0)

        assert data["total_count"] == 5
        assert len(data["object_list"]) == 5
        assert data["limit"] == 10
        assert data["offset"] == 0
        assert data["has_next"] is False
        assert data["has_previous"] is False

    @pytest.mark.asyncio
    async def test_get_objects_with_pagination(self, setup_mixin, products_data):  # noqa: ARG002
        """Pagination returns correct subset."""
        # Verify products_data fixture is available

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductListView)
        data = await mixin.get_objects(limit=2, offset=2)

        assert len(data["object_list"]) == 2
        assert data["total_count"] == 5
        assert data["offset"] == 2
        assert data["has_next"] is True
        assert data["has_previous"] is True

    @pytest.mark.asyncio
    async def test_get_objects_with_ordering(self, setup_mixin, products_data):  # noqa: ARG002
        """Objects are ordered correctly."""
        # Verify products_data fixture is available

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductListView)
        data = await mixin.get_objects(limit=10, offset=0, ordering=[("id", "desc")])

        assert data["object_list"][0].id == 5
        assert data["object_list"][-1].id == 1

    @pytest.mark.asyncio
    async def test_get_objects_uses_paginate_by(self, setup_mixin, products_data):  # noqa: ARG002
        """Uses paginate_by when limit not provided."""
        # Verify products_data fixture is available

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            paginate_by = 2

        mixin = setup_mixin(HTMLTestProductListView)
        data = await mixin.get_objects(offset=0)

        assert len(data["object_list"]) == 2
        assert data["limit"] == 2

    @pytest.mark.asyncio
    async def test_get_objects_limit_overrides_paginate_by(
        self,
        setup_mixin,
        products_data,  # noqa: ARG002
    ):
        """Explicit limit parameter overrides paginate_by."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            paginate_by = 2

        mixin = setup_mixin(HTMLTestProductListView)
        data = await mixin.get_objects(limit=3, offset=0)

        assert len(data["object_list"]) == 3
        assert data["limit"] == 3

    @pytest.mark.asyncio
    async def test_get_objects_with_custom_queryset(self, setup_mixin, products_data):  # noqa: ARG002
        """Custom queryset filtering is respected."""

        class PublishedListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            queryset = HTMLTestProduct.objects.filter(
                HTMLTestProduct.published.is_(True)
            )

        mixin = setup_mixin(PublishedListView)
        data = await mixin.get_objects(limit=10, offset=0)

        assert data["total_count"] == 3
        assert len(data["object_list"]) == 3

    @pytest.mark.asyncio
    async def test_get_objects_custom_queryset_override(
        self,
        setup_mixin,
        products_data,  # noqa: ARG002
    ):
        """get_queryset() override is called."""

        class CustomListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

            def get_queryset(self):
                return self.model.objects.filter(HTMLTestProduct.published.is_(True))

        mixin = setup_mixin(CustomListView)
        data = await mixin.get_objects(limit=10, offset=0)

        assert data["total_count"] == 3
        assert all(obj.published for obj in data["object_list"])

    @pytest.mark.asyncio
    async def test_get_objects_empty_list_allow_empty_true(self, setup_mixin):
        """Empty result returns empty list when allow_empty=True."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            allow_empty = True

        mixin = setup_mixin(HTMLTestProductListView)
        data = await mixin.get_objects(limit=10, offset=0)

        assert data["object_list"] == []
        assert data["total_count"] == 0

    @pytest.mark.asyncio
    async def test_get_objects_empty_list_allow_empty_false(
        self,
        setup_mixin,
        products_data,  # noqa: ARG002
    ):
        """Empty result raises 404 when allow_empty=False and no data."""

        # Create a filtered view that returns no results
        class PublishedListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            allow_empty = False

        mixin = setup_mixin(PublishedListView)

        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_objects(limit=10, offset=1000)

        assert excinfo.value.status_code == 404
        assert "HTMLTestProduct" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_get_objects_auto_error_disabled(self, setup_mixin):
        """Empty result returns empty list when auto_error=False."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct
            allow_empty = False

        mixin = setup_mixin(HTMLTestProductListView)
        data = await mixin.get_objects(limit=10, offset=0, auto_error=False)

        assert data["object_list"] == []
        assert data["total_count"] == 0

    @pytest.mark.asyncio
    async def test_get_objects_without_db_session(self):
        """RuntimeError raised when db session not assigned."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = HTMLTestProductListView()
        mixin.db = None

        with pytest.raises(
            RuntimeError,
            match="Database session is required but not set",
        ):
            await mixin.get_objects(limit=10, offset=0)

    @pytest.mark.asyncio
    async def test_get_objects_invalid_ordering_field_skipped(
        self,
        setup_mixin,
        products_data,  # noqa: ARG002
    ):
        """Invalid ordering field is skipped with warning."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductListView)
        data = await mixin.get_objects(
            limit=10,
            offset=0,
            ordering=[("nonexistent_field", "asc"), ("id", "desc")],
        )

        assert len(data["object_list"]) == 5
        # Should still be ordered by id desc (the valid ordering)
        assert data["object_list"][0].id == 5

    @pytest.mark.asyncio
    async def test_get_objects_has_next_calculation(self, setup_mixin, products_data):  # noqa: ARG002
        """has_next flag calculated correctly."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductListView)

        # Page with more items after
        data = await mixin.get_objects(limit=2, offset=0)
        assert data["has_next"] is True

        # Last page
        data = await mixin.get_objects(limit=2, offset=4)
        assert data["has_next"] is False

        # Full fetch
        data = await mixin.get_objects(limit=10, offset=0)
        assert data["has_next"] is False

    @pytest.mark.asyncio
    async def test_get_objects_has_previous_calculation(
        self,
        setup_mixin,
        products_data,  # noqa: ARG002
    ):
        """has_previous flag calculated correctly."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

        mixin = setup_mixin(HTMLTestProductListView)

        # First page
        data = await mixin.get_objects(limit=2, offset=0)
        assert data["has_previous"] is False

        # Not first page
        data = await mixin.get_objects(limit=2, offset=2)
        assert data["has_previous"] is True


class TestDatabaseExceptions:
    """Tests for database error handling."""

    @pytest.mark.asyncio
    async def test_operational_error_returns_503(self, setup_mixin):
        """OperationalError raises HTTPException 503."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

            def get_queryset(self):  # pyright: ignore[reportIncompatibleMethodOverride]
                class MockQuerySet:
                    async def count(self, _db):
                        msg = "Connection lost"
                        raise OperationalError(msg, None, Exception("ERROR"))

                    def filter(self, *_args, **_kwargs):
                        return self

                    def order_by(self, *_args, **_kwargs):
                        return self

                    def limit(self, *_args, **_kwargs):
                        return self

                    def offset(self, *_args, **_kwargs):
                        return self

                return MockQuerySet()

        mixin = setup_mixin(HTMLTestProductListView)

        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_objects(limit=10, offset=0)

        assert excinfo.value.status_code == 503
        assert "temporarily unavailable" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_integrity_error_returns_500(self, setup_mixin):
        """IntegrityError raises HTTPException 500."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

            def get_queryset(self):  # pyright: ignore[reportIncompatibleMethodOverride]
                class MockQuerySet:
                    async def count(self, _db):
                        msg = "Integrity violation"
                        raise IntegrityError(msg, None, Exception("ERROR"))

                    def filter(self, *_args, **_kwargs):
                        return self

                    def order_by(self, *_args, **_kwargs):
                        return self

                    def limit(self, *_args, **_kwargs):
                        return self

                    def offset(self, *_args, **_kwargs):
                        return self

                return MockQuerySet()

        mixin = setup_mixin(HTMLTestProductListView)

        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_objects(limit=10, offset=0)

        assert excinfo.value.status_code == 500
        assert "Internal database error occurred" in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_database_error_returns_500(self, setup_mixin):
        """DatabaseError raises HTTPException 500."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

            def get_queryset(self):  # pyright: ignore[reportIncompatibleMethodOverride]
                class MockQuerySet:
                    async def count(self, _db):
                        msg = "Database error"
                        raise DatabaseError(msg, None, Exception("ERROR"))

                    def filter(self, *_args, **_kwargs):
                        return self

                    def order_by(self, *_args, **_kwargs):
                        return self

                    def limit(self, *_args, **_kwargs):
                        return self

                    def offset(self, *_args, **_kwargs):
                        return self

                return MockQuerySet()

        mixin = setup_mixin(HTMLTestProductListView)

        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_objects(limit=10, offset=0)

        assert excinfo.value.status_code == 500
        assert "Internal database error occurred." in excinfo.value.detail

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_500(self, setup_mixin):
        """Unexpected exception raises HTTPException 500."""

        class HTMLTestProductListView(MultipleObjectMixin[HTMLTestProduct]):
            model = HTMLTestProduct

            def get_queryset(self):  # pyright: ignore[reportIncompatibleMethodOverride]
                class MockQuerySet:
                    async def count(self, _db):
                        msg = "Unexpected error"
                        raise ValueError(msg)

                    def filter(self, *_args, **_kwargs):
                        return self

                    def order_by(self, *_args, **_kwargs):
                        return self

                    def limit(self, *_args, **_kwargs):
                        return self

                    def offset(self, *_args, **_kwargs):
                        return self

                return MockQuerySet()

        mixin = setup_mixin(HTMLTestProductListView)

        with pytest.raises(HTTPException) as excinfo:
            await mixin.get_objects(limit=10, offset=0)

        assert excinfo.value.status_code == 500
        assert "Internal server error" in excinfo.value.detail
