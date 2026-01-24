from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request, Response
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
        class BlogView(DetailView[Blog]):
            model = Blog
            template_name = "blog_detail.html"

        app.add_api_route("/blog/{slug}", BlogView.as_view())
        response = client.get("/blog/first-post")
        assert "Post: First Post" in response.text

    def test_should_prioritize_pk_over_slug_when_both_present(
        self, app: FastAPI, client
    ):
        class HybridView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

        app.add_api_route("/hybrid/{pk}/{slug}", HybridView.as_view())
        # pk=1 is Laptop. slug='phone-max' is Phone.
        response = client.get("/hybrid/1/phone-max")
        assert "Product: Laptop" in response.text

    def test_should_raise_404_when_object_is_missing(self, app: FastAPI, client):
        class MissingView(DetailView[Product]):
            model = Product
            template_name = "product_detail.html"

        app.add_api_route("/missing/{pk}", MissingView.as_view())
        assert client.get("/missing/999").status_code == 404

    def test_should_use_custom_context_key_when_configured(self, app: FastAPI, client):
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

    @pytest.mark.asyncio
    async def test_force_detail_view_coverage(self, db_session):
        from flash_html.views.generic.detail import DetailView

        # Direct instantiation bypasses the as_view signature logic
        view = DetailView()
        view.model = Product
        view.db = db_session
        view.kwargs = {"pk": 1}
        view.template_name = "product_detail.html"
        view.request = MagicMock(spec=Request)

        await view.get()

        assert view.object is not None
        assert view.object.id == 1
        assert view.object.name == "Laptop"

        context = view.get_context_data()
        assert "product" in context
        assert context["product"] == view.object
