import pytest
from fastapi import FastAPI, Request, Response
from flash_html.template_manager import TemplateManager
from flash_html.views.mixins.template_response import TemplateResponseMixin


class TestTemplateResponseMixin:
    """Test suite specifically for TemplateResponseMixin logic."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Creates a real manager with a temporary template directory."""
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        (tpl_dir / "test.html").write_text("Hello {{ user }}")

        return TemplateManager(project_root=tmp_path)

    def test_get_template_names_valid(self):
        """
        Requirement: Returns [template_name] if set.
        """
        mixin = TemplateResponseMixin()
        mixin.template_name = "index.html"
        assert mixin.get_template_names() == ["index.html"]

    def test_get_template_names_missing(self):
        """
        Requirement: Raises ValueError if template_name is missing.
        """
        mixin = TemplateResponseMixin()
        mixin.template_name = None
        with pytest.raises(ValueError) as exc:
            mixin.get_template_names()
        assert "requires either a definition" in str(exc.value)

    def test_resolve_engine_from_instance(self, manager):
        """
        Requirement: Uses self.template_engine if set (e.g. via as_view injection).
        """
        mixin = TemplateResponseMixin()
        mixin.template_name = "test.html"
        mixin.template_engine = manager

        # We mock request because TemplateResponse expects it in context,
        # but we don't need it to be functional for this simple template.
        # Using a simple object or MagicMock is fine here as a placeholder.
        mixin.request = Request({"type": "http"})

        response = mixin.render_to_response({"user": "World"})

        assert isinstance(response, Response)
        assert b"Hello World" in response.body

    def test_resolve_engine_from_app_state(self, manager):
        """
        Requirement: Resolves engine from request.app.state.template_manager
                if not on instance.
        """
        mixin = TemplateResponseMixin()
        mixin.template_name = "test.html"

        # Setup FastAPI App State
        app = FastAPI()
        app.state.template_manager = manager

        # Create a request linked to that app
        request = Request({"type": "http", "app": app})
        mixin.request = request

        response = mixin.render_to_response({"user": "State"})

        assert isinstance(response, Response)
        assert b"Hello State" in response.body

    def test_engine_not_found_error(self):
        """
        Requirement: Raises RuntimeError if engine is nowhere to be found.
        """
        mixin = TemplateResponseMixin()
        mixin.template_name = "test.html"

        # Even with a request, if state is empty...
        app = FastAPI()  # Empty state
        request = Request({"type": "http", "app": app})
        mixin.request = request

        with pytest.raises(RuntimeError) as exc:
            mixin.render_to_response({})
        assert "Template engine not found" in str(exc.value)

    def test_request_missing_error(self, manager):
        """
        Requirement: Raises RuntimeError if request is not set on the view.
        """
        mixin = TemplateResponseMixin()
        mixin.template_name = "test.html"
        mixin.template_engine = manager

        with pytest.raises(RuntimeError) as exc:
            mixin.render_to_response({})
        assert "Request not set on view" in str(exc.value)

    def test_context_request_injection(self, manager):
        """
        Requirement: 'request' object is injected into the context for Jinja2.
        """
        mixin = TemplateResponseMixin()
        mixin.template_name = "test.html"
        mixin.template_engine = manager

        # Create a request object
        request = Request({"type": "http"})
        mixin.request = request

        context = {"user": "test"}
        # Render
        response = mixin.render_to_response(context)

        # Verify rendering succeeded with the real engine
        assert b"Hello test" in response.body
