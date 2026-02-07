"""
Views for the blog example application.

This module demonstrates various view patterns using the Flash Framework:
- TemplateView for static pages
- DetailView for individual article display
- Custom views for article listing and creation
"""

import logging
import math
from collections.abc import Mapping
from typing import Any, ClassVar

from fastapi import Depends, Response, status
from fastapi.responses import RedirectResponse
from flash_authentication import AnonymousUser
from flash_authentication.models import User
from flash_authentication_session.backend import SessionAuthenticationBackend
from flash_authorization.permissions import (
    AllowAny,
    IsAuthenticated,
    IsStaffUser,
    IsSuperUser,
)
from flash_db import get_db
from flash_html.forms import BaseForm
from flash_html.views.forms import FormView
from flash_html.views.generic.base import TemplateView
from flash_html.views.generic.detail import DetailView
from flash_html.views.mixins import SingleObjectMixin
from flash_html.views.mixins.permission import PermissionMixin
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from .forms import ProfileForm
from .models import Article
from .permissions import ArticleOwnerPermission

logger = logging.getLogger(__name__)


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


def _read_time_minutes(text: str) -> int:
    words = len(text.split())
    return max(1, math.ceil(words / 220))


def _pagination_window(
    page: int,
    total_pages: int,
    *,
    window: int = 2,
) -> tuple[list[int], bool, bool]:
    if total_pages <= 1:
        return [1], False, False
    start = max(1, page - window)
    end = min(total_pages, page + window)
    if end - start < window * 2:
        if start == 1:
            end = min(total_pages, start + window * 2)
        elif end == total_pages:
            start = max(1, end - window * 2)
    page_range = list(range(start, end + 1))
    return page_range, start > 1, end < total_pages


class HomeView(SingleObjectMixin[Article], PermissionMixin, TemplateView):
    """Home page view showing recent articles."""

    template_name = "dashboard.html"
    model = Article  # Required for SingleObjectMixin to auto-inject self.db
    permission_classes: ClassVar[list] = [AllowAny]

    async def get(
        self,
        *args,  # noqa: ARG002
        **kwargs,  # noqa: ARG002
    ) -> Response:
        """Handle GET request with database session."""
        assert self.db
        user = self.request.state.user

        # Get recent articles using auto-injected self.db
        articles = (
            await Article.objects.filter(Article.published.is_(True))
            .order_by(Article.id.desc())
            .limit(5)
            .fetch(self.db)
        )

        user_articles = []
        if user and user.is_active:
            user_articles = (
                await Article.objects.filter(Article.author_id == user.id)
                .order_by(Article.id.desc())
                .limit(5)
                .fetch(self.db)
            )

        # Render template with context
        context = self.get_context_data(
            recent_articles=articles,
            user_articles=user_articles,
        )
        return self.render_to_response(context)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "Flash Blog"
        return context


class ArticleListView(PermissionMixin, SingleObjectMixin[Article], TemplateView):
    """List all published articles."""

    model = Article  # Required for SingleObjectMixin
    permission_classes: ClassVar[list] = [AllowAny]
    template_name = "articles/list.html"

    async def get(self) -> Response:
        """Get list of all published articles."""
        # Check database session is available
        if not self.db:
            return Response("Database session not available", status_code=500)

        status_filter = self.request.query_params.get("status", "").lower()
        page_param = self.request.query_params.get("page", "1")
        query = self.request.query_params.get("q", "").strip()
        try:
            page = max(1, int(page_param))
        except ValueError:
            page = 1
        page_size = 12
        user = self.request.state.user
        messages: dict[str, str] = {}

        if status_filter == "draft":
            if not (user and user.is_active):
                articles = []
                total_count = 0
                messages["info"] = "Sign in to view your drafts."
                total_pages = 1
                page = 1
            else:
                queryset = Article.objects.filter(
                    Article.author_id == user.id,
                    Article.published.is_(False),
                )
                if query:
                    queryset = queryset.filter(
                        or_(
                            Article.title.ilike(f"%{query}%"),
                            Article.content.ilike(f"%{query}%"),
                        )
                    )
                total_count = await queryset.count(self.db)
                total_pages = max(1, math.ceil(total_count / page_size))
                page = min(page, total_pages)
                articles = (
                    await queryset.order_by(Article.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                    .fetch(self.db)
                )
        elif status_filter == "published":
            queryset = Article.objects.filter(Article.published.is_(True))
            if query:
                queryset = queryset.filter(
                    or_(
                        Article.title.ilike(f"%{query}%"),
                        Article.content.ilike(f"%{query}%"),
                    )
                )
            total_count = await queryset.count(self.db)
            total_pages = max(1, math.ceil(total_count / page_size))
            page = min(page, total_pages)
            articles = (
                await queryset.order_by(Article.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .fetch(self.db)
            )
        else:
            if user and user.is_active:
                queryset = Article.objects.filter(
                    or_(
                        Article.published.is_(True),
                        Article.author_id == user.id,
                    )
                )
            else:
                queryset = Article.objects.filter(Article.published.is_(True))
            if query:
                queryset = queryset.filter(
                    or_(
                        Article.title.ilike(f"%{query}%"),
                        Article.content.ilike(f"%{query}%"),
                    )
                )

            total_count = await queryset.count(self.db)
            total_pages = max(1, math.ceil(total_count / page_size))
            page = min(page, total_pages)
            articles = (
                await queryset.order_by(Article.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .fetch(self.db)
            )

        page_range, show_leading, show_trailing = _pagination_window(
            page,
            total_pages,
        )

        context = self.get_context_data(
            articles=articles,
            title="Articles",
            active_status=status_filter,
            messages=messages,
            page=page,
            total_pages=total_pages,
            total_count=total_count,
            query=query,
            page_range=page_range,
            show_leading=show_leading,
            show_trailing=show_trailing,
        )
        for article in articles:
            article.read_time = _read_time_minutes(article.content)  # pyright: ignore[reportAttributeAccessIssue]
        return self.render_to_response(context)


class ArticleDetailView(DetailView[Article]):
    """Display individual article details."""

    model = Article
    template_name = "articles/detail.html"
    context_object_name = "article"
    permission_classes: ClassVar[list] = [
        AllowAny
    ]  # Anyone can view published articles

    def get_queryset(self):
        """Return published articles and owner's drafts when authenticated."""
        queryset = super().get_queryset()
        user = self.request.state.user
        if user and user.is_active:
            return queryset.filter(
                or_(
                    Article.published.is_(True),
                    Article.author_id == user.id,
                )
            )
        return queryset.filter(Article.published.is_(True))

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.state.user
        assert self.object
        context["can_edit"] = bool(
            user
            and user.is_active
            and (user.is_superuser or user.id == self.object.author_id)
        )
        context["read_time"] = _read_time_minutes(self.object.content)
        context.setdefault("messages", {})
        return context


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

        existing = await Article.objects.filter(Article.slug == cleaned["slug"]).first(
            db
        )
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
        await db.commit()

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
    permission_classes: ClassVar[list] = [IsAuthenticated, ArticleOwnerPermission]
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
        await self.check_object_permissions(obj=self.object)
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

        existing = await Article.objects.filter(Article.slug == cleaned["slug"]).first(
            db
        )
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
        await db.commit()

        return RedirectResponse(
            url=f"/articles/{cleaned['slug']}",
            status_code=status.HTTP_303_SEE_OTHER,
        )


class AboutView(PermissionMixin, TemplateView):
    """About page view."""

    template_name = "about.html"
    permission_classes: ClassVar[list] = [AllowAny]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["title"] = "About Our Blog"
        return context


class FormShowcaseView(PermissionMixin, FormView):
    template_name = "forms/showcase.html"
    permission_classes: ClassVar[list] = [AllowAny]
    form_class = ProfileForm
    success_url = "/forms"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("messages", {})
        context["title"] = "Form Showcase"
        return context

    async def form_valid(self, _form: BaseForm) -> Response:
        context = self.get_context_data(
            form=_form,
            messages={"success": "Profile form submitted successfully."},
        )
        return self.render_to_response(context)


class LoginView(PermissionMixin, TemplateView):
    template_name = "auth/login.html"
    success_url = "/"
    permission_classes: ClassVar[list] = [AllowAny]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("messages", {})
        return context

    async def get(self, *args: Any, **kwargs: Any) -> Response:
        next_url = self.request.query_params.get("next")
        if self.request.state.user.is_active:
            return RedirectResponse(
                url=next_url or self.success_url,
                status_code=status.HTTP_303_SEE_OTHER,
            )

        return await super().get(*args, **kwargs)

    async def post(
        self,
        db: AsyncSession = Depends(get_db),
        **kwargs: Any,  # noqa: ARG002
    ) -> Response:
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


class RegisterView(PermissionMixin, TemplateView):
    template_name = "auth/register.html"
    success_url = "/"
    permission_classes: ClassVar[list] = [AllowAny]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context.setdefault("messages", {})
        return context

    async def get(self, *args: Any, **kwargs: Any) -> Response:
        if self.request.state.user.is_active:
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

        existing = await User.objects.filter(User.username == username).first(db)
        if existing:
            context = self.get_context_data(
                messages={"error": "Username already exists."},
            )
            return self.render_to_response(context)

        if email:
            existing_email = await User.objects.filter(User.email == email).first(db)
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


class LogoutView(PermissionMixin, TemplateView):
    template_name = "auth/logout.html"
    success_url = "/login"
    permission_classes: ClassVar[list] = [AllowAny]

    async def get(self, *args: Any, **kwargs: Any) -> Response:  # noqa: ARG002
        user = self.request.state.user
        message = (
            "Use the logout button to end your session."
            if user.is_active
            else "You are already signed out."
        )
        context = self.get_context_data(flash_message=message)
        return self.render_to_response(context)

    async def post(self, db: AsyncSession = Depends(get_db)) -> Response:
        if not self.request.state.user.is_active:
            return RedirectResponse(
                url=self.success_url,
                status_code=status.HTTP_303_SEE_OTHER,
            )
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


class AdminDashboardView(PermissionMixin, TemplateView):
    template_name = "admin/dashboard.html"
    permission_classes: ClassVar[list] = [IsStaffUser]
    login_url = "/login"

    async def get(self, db: AsyncSession = Depends(get_db)) -> Response:
        total_articles = await Article.objects.all().count(db)
        published = await Article.objects.filter(Article.published.is_(True)).count(db)
        drafts = await Article.objects.filter(Article.published.is_(False)).count(db)
        total_users = await User.objects.all().count(db)
        active_users = await User.objects.filter(User.is_active.is_(True)).count(db)
        staff_users = await User.objects.filter(User.is_staff.is_(True)).count(db)

        context = self.get_context_data(
            stats={
                "total_articles": total_articles,
                "published": published,
                "drafts": drafts,
                "pending_drafts": drafts,
                "total_users": total_users,
                "active_users": active_users,
                "staff_users": staff_users,
            }
        )
        return self.render_to_response(context)


class AdminUsersView(PermissionMixin, TemplateView):
    template_name = "admin/users.html"
    permission_classes: ClassVar[list] = [IsSuperUser]
    login_url = "/login"

    async def get(self, db: AsyncSession = Depends(get_db)) -> Response:
        users = await User.objects.all().order_by(User.id.desc()).fetch(db)
        context = self.get_context_data(users=users, messages={})
        return self.render_to_response(context)

    async def post(self, db: AsyncSession = Depends(get_db)) -> Response:
        form_data = await self.request.form()
        user_id = _form_value(form_data, "user_id")
        action = _form_value(form_data, "action")
        actor = self.request.state.user

        messages: dict[str, str] = {}
        if not user_id.isdigit():
            messages["error"] = "Invalid user ID."
            users = await User.objects.all().order_by(User.id.desc()).fetch(db)
            context = self.get_context_data(users=users, messages=messages)
            return self.render_to_response(context)

        target = await db.get(User, int(user_id))
        if not target:
            messages["error"] = "User not found."
            users = await User.objects.all().order_by(User.id.desc()).fetch(db)
            context = self.get_context_data(users=users, messages=messages)
            return self.render_to_response(context)

        current_user = self.request.state.user
        if (
            current_user.is_active
            and current_user.id == target.id
            and action == "deactivate"
        ):
            messages["error"] = "You cannot deactivate your own account."
        else:
            if action == "deactivate":
                target.is_active = False
                messages["success"] = f"Deactivated {target.username}."
                logger.info(
                    "Admin action: deactivate user",
                    extra={"actor_id": actor.id, "target_id": target.id},
                )
            elif action == "activate":
                target.is_active = True
                messages["success"] = f"Activated {target.username}."
                logger.info(
                    "Admin action: activate user",
                    extra={"actor_id": actor.id, "target_id": target.id},
                )
            else:
                messages["error"] = "Unknown action."

            if "success" in messages:
                db.add(target)
                await db.commit()

        users = await User.objects.all().order_by(User.id.desc()).fetch(db)
        context = self.get_context_data(users=users, messages=messages)
        return self.render_to_response(context)


class AdminModerationView(PermissionMixin, TemplateView):
    template_name = "admin/moderation.html"
    permission_classes: ClassVar[list] = [IsStaffUser]
    login_url = "/login"

    async def get(self, db: AsyncSession = Depends(get_db)) -> Response:
        drafts_query = Article.objects.filter(Article.published.is_(False))
        articles = await drafts_query.order_by(Article.id.desc()).fetch(db)
        draft_count = await drafts_query.count(db)
        published_count = await Article.objects.filter(
            Article.published.is_(True)
        ).count(db)
        context = self.get_context_data(
            articles=articles,
            messages={},
            stats={
                "drafts": draft_count,
                "published": published_count,
            },
        )
        return self.render_to_response(context)

    async def post(self, db: AsyncSession = Depends(get_db)) -> Response:
        form_data = await self.request.form()
        article_id = _form_value(form_data, "article_id")
        action = _form_value(form_data, "action")
        actor = self.request.state.user
        messages: dict[str, str] = {}

        if action in {"publish_all", "unpublish_all"}:
            if action == "publish_all":
                updated = await Article.objects.filter(
                    Article.published.is_(False)
                ).update(db, published=True)
                messages["success"] = f"Published {updated} drafts."
            else:
                updated = await Article.objects.filter(
                    Article.published.is_(True)
                ).update(db, published=False)
                messages["success"] = f"Unpublished {updated} articles."

            await db.commit()
            logger.info(
                "Admin action: bulk moderation",
                extra={"actor_id": actor.id, "action": action},
            )
        elif not article_id.isdigit():
            messages["error"] = "Invalid article ID."
        else:
            article = await db.get(Article, int(article_id))
            if not article:
                messages["error"] = "Article not found."
            else:
                if action == "publish":
                    article.published = True
                    messages["success"] = f"Published '{article.title}'."
                elif action == "unpublish":
                    article.published = False
                    messages["success"] = f"Unpublished '{article.title}'."
                else:
                    messages["error"] = "Unknown action."

                if "success" in messages:
                    db.add(article)
                    await db.commit()
                    logger.info(
                        "Admin action: moderation update",
                        extra={
                            "actor_id": actor.id,
                            "article_id": article.id,
                            "action": action,
                        },
                    )

        drafts_query = Article.objects.filter(Article.published.is_(False))
        articles = await drafts_query.order_by(Article.id.desc()).fetch(db)
        draft_count = await drafts_query.count(db)
        published_count = await Article.objects.filter(
            Article.published.is_(True)
        ).count(db)
        context = self.get_context_data(
            articles=articles,
            messages=messages,
            stats={
                "drafts": draft_count,
                "published": published_count,
            },
        )
        return self.render_to_response(context)
