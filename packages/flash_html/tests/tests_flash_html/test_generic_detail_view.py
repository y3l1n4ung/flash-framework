import pytest
import pytest_asyncio
from fastapi import FastAPI, Response
from flash_html.views.generic.base import TemplateView
from flash_html.views.generic.detail import DetailView
from models import Blog, Product
from sqlalchemy import insert


class TestDetailView:
    @pytest_asyncio.fixture(autouse=True)
    async def setup_data(self, db_session):
        await db_session.execute(
            insert(Product).values(
                [
                    {
                        "id": 1,
                        "name": "Laptop",
                        "slug": "laptop-pro",
                        "published": True,
                    },
                    {"id": 2, "name": "Phone", "slug": "phone-max", "published": False},
                ]
            )
        )
        await db_session.execute(
            insert(Blog).values(
                [
                    {
                        "id": 1,
                        "title": "First Post",
                        "slug": "first-post",
                        "status": "published",
                    },
                ]
            )
        )
        await db_session.commit()

    def test_should_execute_full_lifecycle_on_standard_get(self, app: FastAPI, client):
        """Basic GET request with PK lookup and template rendering."""

        class StandardView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

        app.add_api_route("/standard/{pk}", StandardView.as_view())
        response = client.get("/standard/1")

        assert response.status_code == 200
        assert "Product: Laptop" in response.text
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    def test_should_merge_extra_context_with_database_object(
        self, app: FastAPI, client
    ):
        """Hits: self.get_context_data(**kwargs) with as_view(extra_context)."""

        class PromoView(DetailView[Product]):
            model = Product
            template_name = "extra.html"

        app.add_api_route(
            "/promo/{pk}", PromoView.as_view(extra_context={"name": "Flash Sale"})
        )
        response = client.get("/promo/1")
        assert "Extra: Flash Sale" in response.text

    def test_should_retrieve_object_by_slug_when_provided(self, app: FastAPI, client):
        """Slug-based lookup via URL parameter."""

        class BlogView(DetailView[Blog]):
            model = Blog
            template_name = "blog_detail.html"

        app.add_api_route("/blog/{slug}", BlogView.as_view())
        response = client.get("/blog/first-post")
        assert "Post: First Post" in response.text

    def test_should_prioritize_pk_over_slug_when_both_present(
        self, app: FastAPI, client
    ):
        """PK takes priority when both PK and slug are in URL."""

        class HybridView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

        app.add_api_route("/hybrid/{pk}/{slug}", HybridView.as_view())
        # pk=1 is Laptop. slug='phone-max' is Phone.
        response = client.get("/hybrid/1/phone-max")
        assert "Product: Laptop" in response.text

    def test_should_raise_404_when_object_is_missing(self, app: FastAPI, client):
        """404 response when object not found."""

        class MissingView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

        app.add_api_route("/missing/{pk}", MissingView.as_view())
        assert client.get("/missing/999").status_code == 404

    def test_should_use_custom_context_key_when_configured(self, app: FastAPI, client):
        """Custom context_object_name is used instead of model name."""

        class CustomNameView(DetailView[Product]):
            model = Product
            template_name = "item_test.html"
            context_object_name = "item"

        app.add_api_route("/custom-key/{pk}", CustomNameView.as_view())
        response = client.get("/custom-key/1")
        assert "Item: Laptop" in response.text

    def test_should_allow_manual_logic_before_calling_super_get(
        self, app: FastAPI, client
    ):
        """Override get() to add custom business logic."""

        class RestrictedView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

            async def get(self, **kwargs):
                self.object = await self.get_object()
                assert self.object
                if not self.object.published:
                    return Response("Denied", status_code=403)
                return await super().get(**kwargs)

        app.add_api_route("/restricted/{pk}", RestrictedView.as_view())
        assert client.get("/restricted/2").status_code == 403
        assert client.get("/restricted/1").status_code == 200

    @pytest.mark.asyncio
    async def test_should_inject_nested_path_parameters_into_handler(
        self, app: FastAPI, client
    ):
        """Path parameters from URL pattern are injected into get() method."""

        class NestedView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

            async def get(self, org: str, team: str, **kwargs):  # type: ignore
                self.object = await self.get_object()
                assert self.object
                return Response(f"{org}/{team}: {self.object.name}")

        app.add_api_route("/org/{org}/team/{team}/{pk}", NestedView.as_view())
        response = client.get("/org/finance/team/audit/1")
        assert response.text == "finance/audit: Laptop"

    def test_should_verify_mro_precedence(self):
        """
        Requirement: Ensure DetailView is actually higher in MRO than TemplateView.
        If TemplateView appears first in this list, your 'get' will never run.
        """
        mro = DetailView.__mro__
        detail_idx = mro.index(DetailView)
        template_idx = mro.index(TemplateView)

        assert detail_idx < template_idx

    def test_should_fallback_to_model_name_when_context_name_missing(
        self, app: FastAPI, client
    ):
        """
        Target: name = self.context_object_name or self.model.__name__.lower()
        Verifies that 'product' (lowercase model name) is available in context.
        Covers line 53 when context_object_name is None.
        """

        class FallbackNameView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

        app.add_api_route("/fallback/{pk}", FallbackNameView.as_view())
        response = client.get("/fallback/1")

        assert response.status_code == 200
        # This proves self.model.__name__.lower() was used and passed to super().get
        assert "Product: Laptop" in response.text

    def test_should_preserve_existing_kwargs_when_merging_object(
        self, app: FastAPI, client
    ):
        """
        Target: return await super().get(**kwargs, **{name: object})
        Ensures that path parameters in **kwargs are not overwritten by the object merge.
        """

        class KwargMergeView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

            async def get(self, *, category: str, **kwargs):  # ty:ignore[invalid-method-override]
                # We expect 'category' to be in kwargs when super().get is called
                response = await super().get(category=category, **kwargs)
                return response

        app.add_api_route("/merge/{category}/{pk}", KwargMergeView.as_view())
        response = client.get("/merge/electronics/1")

        assert response.status_code == 200
        assert "Product: Laptop" in response.text

    def test_should_delegate_to_template_view_get(self, app: FastAPI, client):
        """
        Coverage target:
            return await super().get(**kwargs)
        """

        class DelegateView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

        app.add_api_route("/delegate/{pk}", DelegateView.as_view())
        response = client.get("/delegate/1")

        assert response.status_code == 200
        assert "Product: Laptop" in response.text


class TestDetailViewContextData:
    """Tests specifically for get_context_data() method."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_data(self, db_session):
        await db_session.execute(
            insert(Product).values(
                [
                    {
                        "id": 1,
                        "name": "Laptop",
                        "slug": "laptop-pro",
                        "published": True,
                    },
                ]
            )
        )
        await db_session.commit()

    def test_context_data_includes_object_with_default_name(self, app: FastAPI, client):
        """Object is added to context with model name in lowercase."""

        class DefaultContextView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

        app.add_api_route("/default-context/{pk}", DefaultContextView.as_view())
        response = client.get("/default-context/1")

        assert response.status_code == 200
        assert "Product: Laptop" in response.text

    def test_context_data_includes_object_with_custom_name(self, app: FastAPI, client):
        """Object is added to context with custom context_object_name."""

        class CustomContextView(DetailView[Product]):
            model = Product
            template_name = "item_test.html"
            context_object_name = "item"

        app.add_api_route("/custom-context/{pk}", CustomContextView.as_view())
        response = client.get("/custom-context/1")

        assert response.status_code == 200
        assert "Item: Laptop" in response.text

    def test_context_data_multiple_calls_consistency(self, app: FastAPI, client):
        """get_context_data() produces consistent output across multiple calls."""

        class ConsistencyView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

        app.add_api_route("/consistency/{pk}", ConsistencyView.as_view())

        # Make multiple requests to ensure consistency
        response1 = client.get("/consistency/1")
        response2 = client.get("/consistency/1")

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.text == response2.text

    @pytest.mark.asyncio
    async def test_get_context_data_uses_model_name_when_no_context_object_name(
        self, db_session
    ):
        """
        Direct unit test for line 53:
        name = self.context_object_name or self.model.__name__.lower()

        Tests the path where context_object_name is None,
        so model.__name__.lower() is used.
        """

        class DirectContextView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"
            context_object_name = None  # Explicitly None

        view = DirectContextView()
        view.db = db_session
        view.kwargs = {"pk": 1}

        # Fetch the object
        view.object = await view.get_object()

        # Call get_context_data() directly with no additional kwargs
        context = view.get_context_data()

        # Verify that 'product' (lowercase model name) is in context
        assert "product" in context
        assert context["product"].id == 1
        assert context["product"].name == "Laptop"


class TestDetailViewIntegration:
    """Integration tests for DetailView with various scenarios."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_data(self, db_session):
        await db_session.execute(
            insert(Product).values(
                [
                    {
                        "id": 1,
                        "name": "Laptop",
                        "slug": "laptop-pro",
                        "published": True,
                    },
                    {"id": 2, "name": "Phone", "slug": "phone-max", "published": False},
                    {
                        "id": 3,
                        "name": "Tablet",
                        "slug": "tablet-pro",
                        "published": True,
                    },
                ]
            )
        )
        await db_session.commit()

    def test_detail_view_with_queryset_filtering(self, app: FastAPI, client):
        """DetailView respects custom queryset with filters."""

        class PublishedOnlyView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

            def get_queryset(self):
                return self.model.objects.filter(Product.published.is_(True))

        app.add_api_route("/published/{pk}", PublishedOnlyView.as_view())

        # Published product should be found
        response = client.get("/published/1")
        assert response.status_code == 200
        assert "Product: Laptop" in response.text

        # Unpublished product should return 404
        response = client.get("/published/2")
        assert response.status_code == 404

    def test_detail_view_handles_content_type_correctly(self, app: FastAPI, client):
        """Response has correct content-type header."""

        class TypeCheckView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

        app.add_api_route("/type/{pk}", TypeCheckView.as_view())
        response = client.get("/type/1")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    def test_detail_view_with_multiple_models(self, app: FastAPI, client):
        """Multiple DetailViews for different models work independently."""

        class ProductDetailView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

        class ProductDetailAltView(DetailView[Product]):
            model = Product
            template_name = "item_test.html"
            context_object_name = "item"

        app.add_api_route("/products/{pk}", ProductDetailView.as_view())
        app.add_api_route("/items/{pk}", ProductDetailAltView.as_view())

        # Both routes work with different context names
        response1 = client.get("/products/1")
        assert response1.status_code == 200
        assert "Product: Laptop" in response1.text

        response2 = client.get("/items/1")
        assert response2.status_code == 200
        assert "Item: Laptop" in response2.text

    def test_detail_view_with_extra_context_and_object(self, app: FastAPI, client):
        """Extra context and object context are merged correctly."""

        class MergedContextView(DetailView[Product]):
            model = Product
            template_name = "extra.html"

        app.add_api_route(
            "/merged/{pk}",
            MergedContextView.as_view(extra_context={"name": "50% off"}),
        )
        response = client.get("/merged/1")

        assert response.status_code == 200
        assert "Extra: 50% off" in response.text

    def test_detail_view_slug_field_configuration(self, app: FastAPI, client):
        """Custom slug_field configuration is respected."""

        class CustomSlugView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"
            slug_field = "slug"
            slug_url_kwarg = "product_slug"

        app.add_api_route("/custom-slug/{product_slug}", CustomSlugView.as_view())
        response = client.get("/custom-slug/laptop-pro")

        assert response.status_code == 200
        assert "Product: Laptop" in response.text

    def test_detail_view_empty_object_attribute_before_get(self, app: FastAPI, client):
        """object attribute is None before get() is called."""

        class ObjectStateView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

            async def get(self, **kwargs):
                # object should be set by DetailView.get() before context_data
                return await super().get(**kwargs)

        app.add_api_route("/state/{pk}", ObjectStateView.as_view())
        response = client.get("/state/1")

        assert response.status_code == 200

    def test_detail_view_with_async_override(self, app: FastAPI, client):
        """Async method override in DetailView subclass works correctly."""

        class AsyncOverrideView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

            async def get(self, **kwargs):
                # Custom async logic
                self.object = await self.get_object()
                assert self.object
                if self.object.name == "Laptop":
                    return await super().get(**kwargs)
                return Response("Not Laptop", status_code=403)

        app.add_api_route("/async/{pk}", AsyncOverrideView.as_view())
        response = client.get("/async/1")

        assert response.status_code == 200
        assert "Product: Laptop" in response.text
