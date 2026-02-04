from types import SimpleNamespace
from typing import ClassVar

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from flash_authorization.permissions import BasePermission
from flash_html.views.generic.detail import DetailView
from flash_html.views.mixins.permission import PermissionMixin
from sqlalchemy import insert

from .models import Article


class TestArticleAuthorPermission(BasePermission):
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
        obj: Article,
        user,
    ) -> bool:
        user_id = obj.author_id

        return user_id == user.id


class TestDetailViewWithCustomPermission:
    """Test DetailView with custom permission."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_data(self, db_session, test_user):

        await db_session.execute(
            insert(Article).values(
                {
                    "id": 1,
                    "title": "Test Article",
                    "slug": "test-article",
                    "content": "Test content",
                    "author_id": test_user.id,
                    "published": True,
                },
            ),
        )
        await db_session.commit()

    def test_custom_permission_works(self, app: FastAPI, client, test_user):
        """Custom permission works correctly."""

        class ArticleDetailView(DetailView[Article]):
            model = Article
            template_name = "article_detail.html"
            permission_classes: ClassVar[list[type[BasePermission]]] = [
                TestArticleAuthorPermission
            ]

        app.add_api_route("/articles/{pk}", ArticleDetailView.as_view())
        app.state.test_user = test_user

        response = client.get("/articles/1")

        assert response.status_code == 200
        assert "Test Article" in response.text

    def test_unauthenticated_blocked(self, app: FastAPI, client):
        """Unauthenticated users are blocked by custom permission."""

        class ArticleDetailView(DetailView[Article]):
            model = Article
            template_name = "article_detail.html"
            permission_classes: ClassVar[list[type[BasePermission]]] = [
                TestArticleAuthorPermission
            ]

        app.add_api_route("/articles/{pk}", ArticleDetailView.as_view())

        response = client.get("/articles/1")

        assert response.status_code == 403


class TestPermissionMixinUserPreference:
    @pytest.mark.asyncio
    async def test_prefers_self_user_over_request_state(self, test_user):
        class PermissionView(PermissionMixin):
            permission_classes: ClassVar[list[type[BasePermission]]] = [
                TestArticleAuthorPermission
            ]

        view = PermissionView()
        view.user = test_user

        request = Request({"type": "http"})
        request.state.user = SimpleNamespace(is_active=False, id=999)
        view.request = request  # type: ignore[assignment]

        article = Article(
            id=1,
            title="Test",
            slug="test",
            content="content",
            author_id=test_user.id,
            published=True,
        )

        # Should not raise, because self.user is preferred.
        await view.check_object_permissions(article)

    @pytest.mark.asyncio
    async def test_fallbacks_to_request_state_user(self):
        class PermissionView(PermissionMixin):
            permission_classes: ClassVar[list[type[BasePermission]]] = [
                TestArticleAuthorPermission
            ]

        view = PermissionView()

        request = Request({"type": "http"})
        request.state.user = SimpleNamespace(is_active=True, id=1)
        view.request = request  # type: ignore[assignment]

        article = Article(
            id=1,
            title="Test",
            slug="test",
            content="content",
            author_id=1,
            published=True,
        )

        # Should not raise, because it falls back to request.state.user.
        await view.check_object_permissions(article)
