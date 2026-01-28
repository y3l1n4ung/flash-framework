from typing import Any

import pytest
from flash_html.template_manager import TemplateManager
from flash_html.views.generic.base import TemplateView


class TestTemplateView:
    """Test suite for TemplateView."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Creates a real manager with a temporary template directory."""
        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        (tpl_dir / "hello.html").write_text("Hello {{ name }}")

        return TemplateManager(project_root=tmp_path)

    def test_basic_rendering(self, app, client):
        """
        Requirement: TemplateView renders HTML using the app state engine.
        """

        class HelloView(TemplateView):
            template_name = "hello.html"

            def get_context_data(self, **kwargs):
                context = super().get_context_data(**kwargs)
                context["name"] = "World"
                return context

        app.add_api_route("/hello", HelloView.as_view())

        response = client.get("/hello")
        assert response.status_code == 200
        assert "Hello World" in response.text
        assert "text/html" in response.headers["content-type"]

    def test_override_via_as_view(self, app, client):
        """
        Requirement: template_name can be overridden in as_view.
        """

        # Define view without template_name
        class GenericView(TemplateView):
            pass

        app.add_api_route(
            "/override",
            GenericView.as_view(
                template_name="hello.html",
                extra_context={"name": "Override"},
            ),
        )

        response = client.get("/override")
        assert response.status_code == 200
        assert "Hello Override" in response.text

    def test_missing_template_raises_error(self, app, client):
        """
        Requirement: Raise ValueError if template_name is not provided.
        """

        class BadView(TemplateView):
            pass  # No template_name

        app.add_api_route("/bad", BadView.as_view())

        # We expect a 500 error because the exception happens inside the view handler
        with pytest.raises(ValueError):
            client.get("/bad")

    def test_subclass_path_parameters(self, app, client):
        """
        Requirement: Subclasses can override get() to accept path parameters.
        FastAPI should correctly route {item_id} to the method argument.
        """

        class ItemView(TemplateView):
            template_name = "hello.html"

            async def get(self, item_id: int):  # type: ignore
                # Pass param to context to verify it was received
                context = self.get_context_data(name=f"Item {item_id}")
                return self.render_to_response(context)

        app.add_api_route("/items/{item_id}", ItemView.as_view())

        response = client.get("/items/42")
        assert response.status_code == 200
        assert "Hello Item 42" in response.text

        # Verify strict typing from FastAPI still works
        response = client.get("/items/not-a-number")
        assert response.status_code == 422

    def test_subclass_query_parameters(self, app, client):
        """
        Requirement: Subclasses can override get() to accept query parameters.
        """

        class SearchView(TemplateView):
            template_name = "hello.html"

            async def get(self, q: str = "Default", **_kwargs: Any):
                context = self.get_context_data(name=q)
                return self.render_to_response(context)

        app.add_api_route("/search", SearchView.as_view())

        # 1. Default value
        response = client.get("/search")
        assert "Hello Default" in response.text

        # 2. With query param
        response = client.get("/search?q=Query")
        assert "Hello Query" in response.text

    def test_base_view_ignores_args_kwargs(self, app, client):
        """
        Requirement: The base get() does not accept *args/**kwargs.
        This ensures FastAPI does NOT interpret them as required query params,
        fixing the 422 Unprocessable Entity issue.
        """

        class SimpleView(TemplateView):
            template_name = "hello.html"
            extra_context = {"name": "Simple"}  # noqa: RUF012

        app.add_api_route("/simple", SimpleView.as_view())

        # This call previously failed with 422 when base get() had **kwargs
        response = client.get("/simple")
        assert response.status_code == 200
        assert "Hello Simple" in response.text

    def test_extra_query_params_are_ignored(self, app, client):
        """
        Requirement: Passing undefined query parameters to a view that hasn't
        explicitly defined them should not cause errors, even if **kwargs exists
        on the base method. They should be ignored by FastAPI's dependency injection
        if filtered by as_view.
        """

        class LooseView(TemplateView):
            template_name = "hello.html"
            extra_context = {"name": "Loose"}  # noqa: RUF012

        app.add_api_route("/loose", LooseView.as_view())

        # Passing ?unexpected=1 should not cause 422 validation error
        response = client.get("/loose?unexpected=1&foo=bar")
        assert response.status_code == 200
        assert "Hello Loose" in response.text

    def test_args_kwargs_in_subclass_override(self, app, client):
        """
        If a subclass explicitly defines *args or **kwargs in its get()
        method, it should still work without crashing, though FastAPI won't fill them
        automatically unless configured to. This test primarily ensures as_view logic
        doesn't break when seeing these in a subclass.
        """

        class KwargsView(TemplateView):
            template_name = "hello.html"

            async def get(self, **kwargs):
                name = "Empty" if not kwargs else "Full"
                context = self.get_context_data(name=name)
                return self.render_to_response(context)

        app.add_api_route("/kwargs", KwargsView.as_view())

        response = client.get("/kwargs?something=1")
        assert response.status_code == 200
        assert "Hello Empty" in response.text
