"""
Views for the blog example application.

This module demonstrates various view patterns using the Flash Framework:
- TemplateView for static pages
- DetailView for individual article display
- Custom views for article listing and creation
"""

from collections.abc import Mapping
from typing import Any, ClassVar

from fastapi import Depends, Response, status
from fastapi.responses import RedirectResponse
from flash_authentication import AnonymousUser
from flash_authentication.models import User
from flash_authentication_session.backend import SessionAuthenticationBackend
from flash_authorization.permissions import AllowAny, IsAuthenticated
from flash_db import get_db
from flash_html.views.base import View
from flash_html.views.generic.base import TemplateView
from flash_html.views.generic.detail import DetailView
from flash_html.views.mixins import SingleObjectMixin
from flash_html.views.mixins.permission import PermissionMixin
from models import Article
from permissions import ArticleOwnerPermission
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _is_published(form_data: Mapping[str, Any]) -> bool:
    return "publish" in form_data or "published" in form_data


def _article_form_data(
    form_data: Mapping[str, Any] | None = None,
    *,
    article: Article | None = None,
) -> dict[str, Any]:
    if article is not None:
        return {
            "title": article.title,
            "slug": article.slug,
            "content": article.content,
            "published": article.published,
        }
    payload = form_data or {}
    return {
        "title": str(payload.get("title", "")).strip(),
        "slug": str(payload.get("slug", "")).strip(),
        "content": str(payload.get("content", "")).strip(),
        "published": _is_published(payload),
    }


def _form_value(form_data: Mapping[str, Any], key: str) -> str:
    raw = form_data.get(key, "")
    if isinstance(raw, str):
        return raw
    return ""

class HomeView(SingleObjectMixin[Article], TemplateView):
    """Home page view showing recent articles."""

    template_name = "dashboard.html"
    model = Article  # Required for SingleObjectMixin to auto-inject self.db

    async def get(self) -> Response:
        """Handle GET request with database session."""
        # Check database session is available
        if not self.db:
            return Response("Database session not available", status_code=500)

        # Get recent articles using auto-injected self.db
        articles = (
            await Article.objects.filter(Article.published.is_(True))
            .order_by(Article.id.desc())
            .limit(5)
            .fetch(self.db)
        )

        # Render template with context
        context = self.get_context_data(recent_articles=articles)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Flash Blog - Home"
        return context


class ArticleListView(SingleObjectMixin[Article], View):
    """List all published articles."""

    model = Article  # Required for SingleObjectMixin

    async def get(self) -> Response:
        """Get list of all published articles."""
        # Check database session is available
        if not self.db:
            return Response("Database session not available", status_code=500)

        articles = (
            await Article.objects.filter(Article.published.is_(True))
            .order_by(Article.id.desc())
            .fetch(self.db)
        )

        # We need to render this manually since ListView isn't implemented yet
        template_manager = self.request.app.state.template_manager
        context = {
            "request": self.request,
            "articles": articles,
            "title": "All Articles",
        }
        template = template_manager.get_template("articles/list.html")
        html_content = await template.render_async(context)
        return Response(html_content, media_type="text/html")


class ArticleDetailView(DetailView[Article]):
    """Display individual article details."""

    model = Article
    template_name = "articles/detail.html"
    context_object_name = "article"
    permission_classes: ClassVar[list] = [
        AllowAny
    ]  # Anyone can view published articles

    def get_queryset(self):
        """Only return published articles for public view."""
        return super().get_queryset().filter(Article.published.is_(True))


class ArticleCreateView(PermissionMixin, TemplateView):
    """Create a new article (simplified form view)."""

    template_name = "articles/write.html"
    permission_classes: ClassVar[list] = [IsAuthenticated]
    login_url = "/login"

    async def get(self) -> Response:
        """Handle GET request for article creation form."""
        context = self.get_context_data(
            form_data=_article_form_data(),
            messages={},
        )
        context["title"] = "Write New Article"
        context["action"] = "Create"
        return self.render_to_response(context)

    async def post(self, db: AsyncSession = Depends(get_db)) -> Response:
        """Handle article creation."""
        form_data = await self.request.form()
        cleaned = _article_form_data(form_data)

        if not cleaned["title"] or not cleaned["slug"] or not cleaned["content"]:
            context = self.get_context_data(
                form_data=cleaned,
                messages={"error": "Title, slug, and content are required."},
            )
            context["title"] = "Write New Article"
            context["action"] = "Create"
            return self.render_to_response(context)

        existing = await Article.objects.filter(
            Article.slug == cleaned["slug"]
        ).first(db)
        if existing:
            context = self.get_context_data(
                form_data=cleaned,
                messages={"error": "Slug already exists. Choose another."},
            )
            context["title"] = "Write New Article"
            context["action"] = "Create"
            return self.render_to_response(context)

        author_id = self.request.state.user.id

        # Create article
        article = await Article.objects.create(
            db,
            title=cleaned["title"],
            slug=cleaned["slug"],
            content=cleaned["content"],
            author_id=author_id,
            published=cleaned["published"],
        )

        # Redirect to article detail
        return RedirectResponse(
            url=f"/articles/{article.slug}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


class ArticleEditView(DetailView[Article]):
    """Edit existing article."""

    model = Article
    template_name = "articles/write.html"
    context_object_name = "article"
    permission_classes: ClassVar[list] = [ArticleOwnerPermission]
    login_url = "/login"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        if self.object:
            context["title"] = f"Edit: {self.object.title}"
            context["form_data"] = _article_form_data(article=self.object)
        else:
            context["title"] = "Edit Article"
            context["form_data"] = _article_form_data()
        context["action"] = "Update"
        context.setdefault("messages", {})
        return context

    async def post(self, slug: str, db: AsyncSession = Depends(get_db)) -> Response:
        """Handle article update."""
        # Set the slug from URL parameter for get_object
        self.kwargs = {"slug": slug}
        self.object = await self.get_object()

        # Check permissions
        if self.permission_classes and self.object:
            user = self.request.state.user
            permissions = self.get_permissions()
            await self.check_object_permissions(
                request=self.request,
                obj=self.object,
                permissions=permissions,
                user=user,
            )

        # Update article (only if object exists)
        if not self.object:
            return Response("Article not found", status_code=404)

        # Get form data
        form_data = await self.request.form()
        cleaned = _article_form_data(form_data)
        if not cleaned["title"] or not cleaned["slug"] or not cleaned["content"]:
            context = self.get_context_data(
                messages={"error": "Title, slug, and content are required."},
            )
            context["form_data"] = cleaned
            return self.render_to_response(context)

        existing = await Article.objects.filter(
            Article.slug == cleaned["slug"]
        ).first(db)
        if existing and existing.id != self.object.id:
            context = self.get_context_data(
                messages={"error": "Slug already exists. Choose another."},
            )
            context["form_data"] = cleaned
            return self.render_to_response(context)

        await Article.objects.update(
            db,
            self.object.id,
            title=cleaned["title"],
            slug=cleaned["slug"],
            content=cleaned["content"],
            published=cleaned["published"],
        )

        return RedirectResponse(
            url=f"/articles/{self.object.slug}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


class AboutView(TemplateView):
    """About page view."""

    template_name = "about.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "About Our Blog"
        return context


class LoginView(TemplateView):
    template_name = "auth/login.html"
    success_url = "/"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("messages", {})
        return context

    async def get(self, *args: Any, **kwargs: Any) -> Response:
        next_url = self.request.query_params.get("next")
        if self.request.state.user.is_authenticated:
            return RedirectResponse(
                url=next_url or self.success_url,
                status_code=status.HTTP_303_SEE_OTHER,
            )

        return await super().get(*args, **kwargs)

    async def post(self, db: AsyncSession = Depends(get_db)) -> Response:
        form_data = await self.request.form()
        username = _form_value(form_data, "username")
        password = _form_value(form_data, "password")
        next_url = _form_value(form_data, "next") or self.request.query_params.get(
            "next"
        )
        backend = SessionAuthenticationBackend()
        result = await backend.login(
            request=self.request,
            db=db,
            username=username,
            password=password,
            email="",
        )
        if result.success:
            self.request.state.user = result.user
            return RedirectResponse(
                url=next_url or self.success_url,
                status_code=status.HTTP_303_SEE_OTHER,
            )
        context = self.get_context_data(
            messages={"error": result.message},
        )
        return self.render_to_response(context)


class RegisterView(TemplateView):
    template_name = "auth/register.html"
    success_url = "/"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("messages", {})
        return context

    async def get(self, *args: Any, **kwargs: Any) -> Response:
        if self.request.state.user.is_authenticated:
            return RedirectResponse(
                url=self.success_url, status_code=status.HTTP_303_SEE_OTHER
            )
        return await super().get(*args, **kwargs)

    async def post(self, db: AsyncSession = Depends(get_db)) -> Response:
        form_data = await self.request.form()
        username = _form_value(form_data, "username").strip()
        email = _form_value(form_data, "email").strip() or None
        password = _form_value(form_data, "password")
        confirm_password = _form_value(form_data, "confirm_password")

        if not username or not password:
            context = self.get_context_data(
                messages={"error": "Username and password are required."},
            )
            return self.render_to_response(context)

        if password != confirm_password:
            context = self.get_context_data(
                messages={"error": "Passwords do not match."},
            )
            return self.render_to_response(context)

        if len(password) < 8:
            context = self.get_context_data(
                messages={"error": "Password must be at least 8 characters."},
            )
            return self.render_to_response(context)

        existing = await db.scalar(select(User).where(User.username == username))
        if existing:
            context = self.get_context_data(
                messages={"error": "Username already exists."},
            )
            return self.render_to_response(context)

        if email:
            existing_email = await db.scalar(select(User).where(User.email == email))
            if existing_email:
                context = self.get_context_data(
                    messages={"error": "Email already in use."},
                )
                return self.render_to_response(context)

        user = User(
            username=username,
            email=email,
            is_active=True,
        )
        user.set_password(password)
        db.add(user)
        await db.commit()
        await db.refresh(user)

        backend = SessionAuthenticationBackend()
        result = await backend.login(
            request=self.request,
            db=db,
            username=username,
            password=password,
            email=email or "",
        )
        if result.success:
            self.request.state.user = result.user
            return RedirectResponse(
                url=self.success_url,
                status_code=status.HTTP_303_SEE_OTHER,
            )

        context = self.get_context_data(
            messages={"success": "Account created. Please log in."},
        )
        return self.render_to_response(context)


class LogoutView(TemplateView):
    template_name = "auth/logout.html"
    success_url = "/login"

    async def get(self, *args: Any, **kwargs: Any) -> Response:  # noqa: ARG002
        context = self.get_context_data(
            flash_message="Use the logout button to end your session.",
        )
        return self.render_to_response(context)

    async def post(self, db: AsyncSession = Depends(get_db)) -> Response:
        backend = SessionAuthenticationBackend()
        success = await backend.logout(self.request, db)
        self.request.state.user = AnonymousUser()
        message = (
            "You have been successfully logged out."
            if success
            else "You are already logged out."
        )
        context = self.get_context_data(flash_message=message)
        return self.render_to_response(context)
