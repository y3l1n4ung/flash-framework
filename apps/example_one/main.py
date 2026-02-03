"""
Main entry point for the Flash Framework Blog Example.

Run this application with:
    uvicorn main:app --reload

Or using pymelos from the project root:
    pymelos run example_one dev
"""

from contextlib import asynccontextmanager
from os import getenv
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from flash_authentication_session.middleware import SessionAuthenticationMiddleware
from flash_db import db as db_module
from flash_db import init_db
from flash_html.template_manager import TemplateManager
from models import Article
from starlette.middleware.sessions import SessionMiddleware
from views import (
    AboutView,
    ArticleCreateView,
    ArticleDetailView,
    ArticleEditView,
    ArticleListView,
    HomeView,
    LoginView,
    LogoutView,
    RegisterView,
)

init_db("sqlite+aiosqlite:///blog.db", echo=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database

    # Create all tables after init
    engine = db_module._engine
    assert engine is not None
    async with engine.begin() as conn:
        await conn.run_sync(Article.metadata.create_all)
    template_manager = TemplateManager(project_root=Path(__file__).parent)
    app.state.template_manager = template_manager

    _ = app
    yield
    await engine.dispose()


app = FastAPI(
    title="Flash Framework Blog Example",
    description="A blog application demonstrating Flash Framework features",
    version="1.0.0",
    lifespan=lifespan,
)


def register_routes(app: FastAPI) -> None:
    """Register all application routes."""

    # Home page
    app.add_api_route(
        "/",
        HomeView.as_view(method="get"),
        methods=["GET"],
    )

    # Article URLs
    app.add_api_route(
        "/articles/",
        ArticleListView.as_view(method="get"),
        methods=["GET"],
    )
    app.add_api_route(
        "/articles/new",
        ArticleCreateView.as_view(method="get"),
        methods=["GET"],
    )
    app.add_api_route(
        "/articles/new",
        ArticleCreateView.as_view(method="post"),
        methods=["POST"],
    )
    app.add_api_route(
        "/articles/{slug}",
        ArticleDetailView.as_view(method="get"),
        methods=["GET"],
    )
    app.add_api_route(
        "/articles/{slug}/edit",
        ArticleEditView.as_view(method="get"),
        methods=["GET"],
    )
    app.add_api_route(
        "/articles/{slug}/edit",
        ArticleEditView.as_view(method="post"),
        methods=["POST"],
    )

    # About page
    app.add_api_route(
        "/about",
        AboutView.as_view(method="get"),
        methods=["GET"],
    )

    # Auth
    app.add_api_route(
        "/login",
        LoginView.as_view(method="get"),
        methods=["GET"],
    )
    app.add_api_route(
        "/login",
        LoginView.as_view(method="post"),
        methods=["POST"],
    )
    app.add_api_route(
        "/register",
        RegisterView.as_view(method="get"),
        methods=["GET"],
    )
    app.add_api_route(
        "/register",
        RegisterView.as_view(method="post"),
        methods=["POST"],
    )
    app.add_api_route(
        "/logout",
        LogoutView.as_view(method="get"),
        methods=["GET"],
    )
    app.add_api_route(
        "/logout",
        LogoutView.as_view(method="post"),
        methods=["POST"],
    )


# Create app instance

session_factory = db_module._require_session_factory()
app.add_middleware(
    SessionMiddleware,  # ty:ignore[invalid-argument-type]
    secret_key=getenv("FLASH_SECRET_KEY", "flash-dev-secret"),
    https_only=False,
)
app.add_middleware(
    SessionAuthenticationMiddleware,  # ty:ignore[invalid-argument-type]
    session_maker=session_factory,
)

register_routes(app)
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
