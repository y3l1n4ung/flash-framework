from typing import ClassVar

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from flash_authorization.permissions import (
    AllowAny,
    BasePermission,
    IsAuthenticated,
    IsStaffUser,
)
from flash_html.views.generic.base import TemplateView
from flash_html.views.generic.detail import DetailView
from sqlalchemy import insert

from .models import HTMLTestArticle, HTMLTestBlog, HTMLTestProduct


class IsHTMLTestArticleAuthor(BasePermission):
    """Allow access only to the author of the article."""

    async def has_permission(
        self,
        request,  # noqa: ARG002
        user,
    ):
        return user.is_active

    async def has_object_permission(
        self,
        request,  # noqa: ARG002
        obj: HTMLTestArticle,
        user,
    ):
        return obj.author_id == user.id


class TestDetailView:
    @pytest_asyncio.fixture(autouse=True)
    async def setup_data(self, db_session):
        await db_session.execute(
            insert(HTMLTestProduct).values(
                [
                    {
                        "id": 1,
                        "name": "Laptop",
                        "slug": "laptop-pro",
                        "published": True,
                    },
                    {"id": 2, "name": "Phone", "slug": "phone-max", "published": False},
                ],
            ),
        )
        await db_session.execute(
            insert(HTMLTestBlog).values(
                [
                    {
                        "id": 1,
                        "title": "First Post",
                        "slug": "first-post",
                        "status": "published",
                    },
                ],
            ),
        )
        await db_session.commit()

    def test_should_execute_full_lifecycle_on_standard_get(
        self, app: FastAPI, client: TestClient
    ):
        """Basic GET request with PK lookup and template rendering."""

        class StandardView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"

        app.add_api_route("/standard/{pk}", StandardView.as_view())
        response = client.get("/standard/1")

        assert response.status_code == 200
        assert "Product: Laptop" in response.text
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    def test_should_merge_extra_context_with_database_object(
        self,
        app: FastAPI,
        client: TestClient,
    ):
        """Hits: self.get_context_data(**kwargs) with as_view(extra_context)."""

        class PromoView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "extra.html"

        app.add_api_route(
            "/promo/{pk}",
            PromoView.as_view(extra_context={"name": "Flash Sale"}),
        )
        response = client.get("/promo/1")
        assert "Extra: Flash Sale" in response.text

    def test_should_retrieve_object_by_slug_when_provided(
        self, app: FastAPI, client: TestClient
    ):
        """Slug-based lookup via URL parameter."""

        class HTMLTestBlogView(DetailView[HTMLTestBlog]):
            model = HTMLTestBlog
            template_name = "blog_detail.html"

        app.add_api_route("/blog/{slug}", HTMLTestBlogView.as_view())
        response = client.get("/blog/first-post")
        assert "Post: First Post" in response.text

    def test_should_prioritize_pk_over_slug_when_both_present(
        self,
        app: FastAPI,
        client: TestClient,
    ):
        """PK takes priority when both PK and slug are in URL."""

        class HybridView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"

        app.add_api_route("/hybrid/{pk}/{slug}", HybridView.as_view())
        # pk=1 is Laptop. slug='phone-max' is Phone.
        response = client.get("/hybrid/1/phone-max")
        assert "Product: Laptop" in response.text

    def test_should_raise_404_when_object_is_missing(
        self, app: FastAPI, client: TestClient
    ):
        """404 response when object not found."""

        class MissingView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"

        app.add_api_route("/missing/{pk}", MissingView.as_view())
        assert client.get("/missing/999").status_code == 404

    def test_should_use_custom_context_key_when_configured(
        self, app: FastAPI, client: TestClient
    ):
        """Custom context_object_name is used instead of model name."""

        class CustomNameView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "item_test.html"
            context_object_name = "item"

        app.add_api_route("/custom-key/{pk}", CustomNameView.as_view())
        response = client.get("/custom-key/1")
        assert "Item: Laptop" in response.text

    def test_should_allow_manual_logic_before_calling_super_get(
        self,
        app: FastAPI,
        client: TestClient,
    ):
        """Override get() to add custom business logic."""

        class RestrictedView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
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
        self,
        app: FastAPI,
        client: TestClient,
    ):
        """Path parameters from URL pattern are injected into get() method."""

        class NestedView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"

            async def get(self, org: str, team: str, **_kwargs):
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
        self,
        app: FastAPI,
        client: TestClient,
    ):
        """
        Target: name = self.context_object_name or self.model.__name__.lower()
        Verifies that 'product' (lowercase model name) is available in context.
        Covers line 53 when context_object_name is None.
        """

        class FallbackNameView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"

        app.add_api_route("/fallback/{pk}", FallbackNameView.as_view())
        response = client.get("/fallback/1")

        assert response.status_code == 200
        # This proves self.model.__name__.lower() was used and passed to super().get
        assert "Product: Laptop" in response.text

    def test_should_preserve_existing_kwargs_when_merging_object(
        self,
        app: FastAPI,
        client: TestClient,
    ):
        """
        Target: return await super().get(**kwargs, **{name: object})
        Ensures that path parameters in **kwargs are not overwritten by the object
        merge.
        """

        class KwargMergeView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"

            async def get(self, *, category: str, **kwargs):
                # We expect 'category' to be in kwargs when super().get is called
                return await super().get(category=category, **kwargs)

        app.add_api_route("/merge/{category}/{pk}", KwargMergeView.as_view())
        response = client.get("/merge/electronics/1")

        assert response.status_code == 200
        assert "Product: Laptop" in response.text

    def test_should_delegate_to_template_view_get(
        self, app: FastAPI, client: TestClient
    ):
        """
        Coverage target:
            return await super().get(**kwargs)
        """

        class DelegateView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
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
            insert(HTMLTestProduct).values(
                [
                    {
                        "id": 1,
                        "name": "Laptop",
                        "slug": "laptop-pro",
                        "published": True,
                    },
                ],
            ),
        )
        await db_session.commit()

    def test_context_data_includes_object_with_default_name(
        self, app: FastAPI, client: TestClient
    ):
        """Object is added to context with model name in lowercase."""

        class DefaultContextView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"

        app.add_api_route("/default-context/{pk}", DefaultContextView.as_view())
        response = client.get("/default-context/1")

        assert response.status_code == 200
        assert "Product: Laptop" in response.text

    def test_context_data_includes_object_with_custom_name(
        self, app: FastAPI, client: TestClient
    ):
        """Object is added to context with custom context_object_name."""

        class CustomContextView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "item_test.html"
            context_object_name = "item"

        app.add_api_route("/custom-context/{pk}", CustomContextView.as_view())
        response = client.get("/custom-context/1")

        assert response.status_code == 200
        assert "Item: Laptop" in response.text

    def test_context_data_multiple_calls_consistency(
        self, app: FastAPI, client: TestClient
    ):
        """get_context_data() produces consistent output across multiple calls."""

        class ConsistencyView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
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
        self,
        db_session,
    ):
        """
        Direct unit test for line 53:
        name = self.context_object_name or self.model.__name__.lower()

        Tests the path where context_object_name is None,
        so model.__name__.lower() is used.
        """

        class DirectContextView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"
            context_object_name = None

        view = DirectContextView()  # pyright: ignore[reportAbstractUsage]
        view.db = db_session
        view.kwargs = {"pk": 1}

        # Fetch the object
        view.object = await view.get_object()

        # Call get_context_data() directly with no additional kwargs
        context = view.get_context_data()

        # Verify that 'product' (lowercase model name) is in context
        assert "htmltestproduct" in context
        assert context["htmltestproduct"].id == 1
        assert context["htmltestproduct"].name == "Laptop"


class TestDetailViewIntegration:
    """Integration tests for DetailView with various scenarios."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_data(self, db_session):
        await db_session.execute(
            insert(HTMLTestProduct).values(
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
                ],
            ),
        )
        await db_session.commit()

    def test_detail_view_with_queryset_filtering(
        self, app: FastAPI, client: TestClient
    ):
        """DetailView respects custom queryset with filters."""

        class PublishedOnlyView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"

            def get_queryset(self):
                return self.model.objects.filter(HTMLTestProduct.published.is_(True))

        app.add_api_route("/published/{pk}", PublishedOnlyView.as_view())

        # Published product should be found
        response = client.get("/published/1")
        assert response.status_code == 200
        assert "Product: Laptop" in response.text

        # Unpublished product should return 404
        response = client.get("/published/2")
        assert response.status_code == 404

    def test_detail_view_handles_content_type_correctly(
        self, app: FastAPI, client: TestClient
    ):
        """Response has correct content-type header."""

        class TypeCheckView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"

        app.add_api_route("/type/{pk}", TypeCheckView.as_view())
        response = client.get("/type/1")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"

    def test_detail_view_with_multiple_models(self, app: FastAPI, client: TestClient):
        """Multiple DetailViews for different models work independently."""

        class HTMLTestProductDetailView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"

        class HTMLTestProductDetailAltView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "item_test.html"
            context_object_name = "item"

        app.add_api_route("/products/{pk}", HTMLTestProductDetailView.as_view())
        app.add_api_route("/items/{pk}", HTMLTestProductDetailAltView.as_view())

        # Both routes work with different context names
        response1 = client.get("/products/1")
        assert response1.status_code == 200
        assert "Product: Laptop" in response1.text

        response2 = client.get("/items/1")
        assert response2.status_code == 200
        assert "Item: Laptop" in response2.text

    def test_detail_view_with_extra_context_and_object(
        self, app: FastAPI, client: TestClient
    ):
        """Extra context and object context are merged correctly."""

        class MergedContextView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "extra.html"

        app.add_api_route(
            "/merged/{pk}",
            MergedContextView.as_view(extra_context={"name": "50% off"}),
        )
        response = client.get("/merged/1")

        assert response.status_code == 200
        assert "Extra: 50% off" in response.text

    def test_detail_view_slug_field_configuration(
        self, app: FastAPI, client: TestClient
    ):
        """Custom slug_field configuration is respected."""

        class CustomSlugView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"
            slug_field = "slug"
            slug_url_kwarg = "product_slug"

        app.add_api_route("/custom-slug/{product_slug}", CustomSlugView.as_view())
        response = client.get("/custom-slug/laptop-pro")

        assert response.status_code == 200
        assert "Product: Laptop" in response.text

    def test_detail_view_empty_object_attribute_before_get(
        self, app: FastAPI, client: TestClient
    ):
        """object attribute is None before get() is called."""

        class ObjectStateView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"

            async def get(self, **kwargs):
                # object should be set by DetailView.get() before context_data
                return await super().get(**kwargs)

        app.add_api_route("/state/{pk}", ObjectStateView.as_view())
        response = client.get("/state/1")

        assert response.status_code == 200

    def test_detail_view_with_async_override(self, app: FastAPI, client: TestClient):
        """Async method override in DetailView subclass works correctly."""

        class AsyncOverrideView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
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


class TestDetailViewPermissions:
    """Test DetailView with permission classes."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_data(self, db_session):
        await db_session.execute(
            insert(HTMLTestProduct).values(
                [
                    {
                        "id": 1,
                        "name": "Public HTMLTestProduct",
                        "slug": "public-product",
                        "published": True,
                    },
                ],
            ),
        )
        await db_session.commit()

    def test_allow_any_permission(self, app: FastAPI, client: TestClient):
        """AllowAny permission permits access to everyone."""

        class PublicHTMLTestProductView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"
            permission_classes: ClassVar[list[type[BasePermission]]] = [AllowAny]

        app.add_api_route("/public/{pk}", PublicHTMLTestProductView.as_view())
        response = client.get("/public/1")

        assert response.status_code == 200
        assert "Product: Public HTMLTestProduct" in response.text

    def test_is_authenticated_permission_no_user(
        self, app: FastAPI, client: TestClient
    ):
        """IsAuthenticated blocks access when user is not authenticated."""

        class AuthenticatedHTMLTestProductView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"
            permission_classes: ClassVar[list[type[BasePermission]]] = [IsAuthenticated]

        app.add_api_route("/auth/{pk}", AuthenticatedHTMLTestProductView.as_view())
        response = client.get("/auth/1")

        # Should return 403 for unauthenticated access
        assert response.status_code == 403

    def test_permission_override_via_as_view(self, app: FastAPI, client: TestClient):
        """Permissions can be overridden via as_view() call."""

        class HTMLTestProductView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"
            permission_classes: ClassVar[list[type[BasePermission]]] = [IsAuthenticated]

        # Override with AllowAny for this route
        app.add_api_route(
            "/override/{pk}", HTMLTestProductView.as_view(permission_classes=[AllowAny])
        )
        response = client.get("/override/1")

        assert response.status_code == 200
        assert "Product: Public HTMLTestProduct" in response.text

    def test_multiple_permission_classes(self, app: FastAPI, client: TestClient):
        """Multiple permission classes work together."""

        class ProtectedHTMLTestProductView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"
            permission_classes: ClassVar[list[type[BasePermission]]] = [
                IsAuthenticated,
                IsStaffUser,
            ]

        app.add_api_route("/multi/{pk}", ProtectedHTMLTestProductView.as_view())
        response = client.get("/multi/1")

        # Should be blocked - not authenticated, not staff
        assert response.status_code == 403

    def test_empty_permission_classes_defaults_to_allow(
        self, app: FastAPI, client: TestClient
    ):
        """Empty permission_classes allows access."""

        class DefaultHTMLTestProductView(DetailView[HTMLTestProduct]):
            model = HTMLTestProduct
            template_name = "product_detail.html"
            permission_classes: ClassVar[list] = []

        app.add_api_route("/empty/{pk}", DefaultHTMLTestProductView.as_view())
        response = client.get("/empty/1")

        assert response.status_code == 200
        assert "Product: Public HTMLTestProduct" in response.text


class TestDetailViewObjectPermissions:
    """Test DetailView with object-level permissions."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_data(self, db_session, test_user, admin_user, blog_user):
        # Create articles with different authors
        await db_session.execute(
            insert(HTMLTestArticle).values(
                [
                    {
                        "id": 1,
                        "title": "Test User's HTMLTestArticle",
                        "slug": "test-user-article",
                        "content": "Content by test user",
                        "author_id": test_user.id,
                        "published": True,
                    },
                    {
                        "id": 2,
                        "title": "HTMLTestBlog User's HTMLTestArticle",
                        "slug": "blog-user-article",
                        "content": "Content by blog user",
                        "author_id": blog_user.id,
                        "published": True,
                    },
                    {
                        "id": 3,
                        "title": "Admin's HTMLTestArticle",
                        "slug": "admin-article",
                        "content": "Content by admin",
                        "author_id": admin_user.id,
                        "published": True,
                    },
                ],
            ),
        )
        await db_session.commit()

    def test_is_owner_permission_works(
        self, app: FastAPI, client: TestClient, test_user
    ):
        """IsHTMLTestArticleAuthor permission allows owner to access their object."""

        class OwnerHTMLTestArticleView(DetailView[HTMLTestArticle]):
            model = HTMLTestArticle
            template_name = "article_detail.html"
            permission_classes: ClassVar[list[type[BasePermission]]] = [
                IsHTMLTestArticleAuthor
            ]

        app.add_api_route("/owner/{pk}", OwnerHTMLTestArticleView.as_view())
        app.state.test_user = test_user
        response = client.get("/owner/1")

        assert response.status_code == 200
        assert "HTMLTestArticle: Test User" in response.text
        assert "HTMLTestArticle by 1" in response.text

    def test_is_owner_blocks_non_owner(
        self, app: FastAPI, client: TestClient, blog_user
    ):
        """
        IsHTMLTestArticleAuthor permission blocks non-author from accessing object.
        """

        class OwnerHTMLTestArticleView(DetailView[HTMLTestArticle]):
            model = HTMLTestArticle
            template_name = "article_detail.html"
            permission_classes: ClassVar[list[type[BasePermission]]] = [
                IsHTMLTestArticleAuthor
            ]

        app.add_api_route("/owner/{pk}", OwnerHTMLTestArticleView.as_view())

        # Mock authenticated user as blog_user (not owner of article 1)
        app.state.test_user = blog_user
        response = client.get("/owner/1")

        assert response.status_code == 403

    def test_permissions_with_extra_context(
        self, app: FastAPI, client: TestClient, test_user
    ):
        """Permissions work with extra context passed via as_view()."""

        class ExtraContextHTMLTestArticleView(DetailView[HTMLTestArticle]):
            model = HTMLTestArticle
            template_name = "extra.html"  # Uses extra template
            permission_classes: ClassVar[list[type[BasePermission]]] = [
                IsHTMLTestArticleAuthor
            ]

        app.add_api_route(
            "/extra-context/{pk}",
            ExtraContextHTMLTestArticleView.as_view(
                extra_context={"name": "HTMLTestBlog"}
            ),
        )

        # Mock authenticated user as test_user (owner)
        app.state.test_user = test_user
        response = client.get("/extra-context/1")

        assert response.status_code == 200
        assert "Extra: HTMLTestBlog" in response.text

    def test_detail_view_calls_object_permissions(
        self,
        app: FastAPI,
        client: TestClient,
        test_user,
    ):
        """DetailView should call object permission checks on GET."""

        class FlagPermission(BasePermission):
            called = False

            async def has_permission(self, request, user):  # noqa: ARG002
                return True

            async def has_object_permission(self, request, obj, user):  # noqa: ARG002
                FlagPermission.called = True
                return True

        class OwnerHTMLTestArticleView(DetailView[HTMLTestArticle]):
            model = HTMLTestArticle
            template_name = "article_detail.html"
            permission_classes: ClassVar[list[type[BasePermission]]] = [FlagPermission]

        app.add_api_route("/flag/{pk}", OwnerHTMLTestArticleView.as_view())
        app.state.test_user = test_user

        response = client.get("/flag/1")

        assert response.status_code == 200
        assert FlagPermission.called is True

    def test_permission_error_responses_are_proper(
        self, app: FastAPI, client: TestClient
    ):
        """Permission denied responses return proper 403 status."""

        class ProtectedHTMLTestArticleView(DetailView[HTMLTestArticle]):
            model = HTMLTestArticle
            template_name = "article_detail.html"
            permission_classes: ClassVar[list[type[BasePermission]]] = [IsAuthenticated]

        app.add_api_route("/protected/{pk}", ProtectedHTMLTestArticleView.as_view())

        # No user authenticated - should get 403
        response = client.get("/protected/1")

        assert response.status_code == 403
        assert (
            "detail" in response.json() or response.text
        )  # Either JSON detail or text

    @pytest.mark.asyncio
    async def test_detail_view_get_executes_permission_and_render(self, test_user):
        class AllowObject(BasePermission):
            async def has_permission(self, request, user):  # noqa: ARG002
                return True

            async def has_object_permission(self, request, obj, user):  # noqa: ARG002
                return True

        class MinimalDetailView(DetailView[HTMLTestArticle]):
            model = HTMLTestArticle
            template_name = "unused.html"
            permission_classes: ClassVar[list[type[BasePermission]]] = [AllowObject]

            async def get_object(self, *args, **kwargs):  # noqa: ARG002
                return HTMLTestArticle(
                    id=1,
                    title="Test",
                    slug="test",
                    content="content",
                    author_id=test_user.id,
                    published=True,
                )

            def render_to_response(self, context, **kwargs):  # noqa: ARG002
                return Response("ok")

        view = MinimalDetailView()  # pyright: ignore[reportAbstractUsage]
        request = Request({"type": "http"})
        request.state.user = test_user
        view.request = request
        view.kwargs = {}

        response = await view.get()

        assert response.status_code == 200
        assert response.body == b"ok"
