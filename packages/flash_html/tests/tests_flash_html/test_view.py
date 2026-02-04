import inspect

import pytest
from fastapi import Depends, FastAPI, Request, Response
from fastapi.testclient import TestClient
from flash_html.views.base import View

# --- Unit Tests: Core View Logic ---


class TestViewBase:
    """Test suite for the internal mechanics of the View class."""

    def test_as_view_strict_validation(self):
        """Requirement: as_view() raises TypeError for invalid attributes to
        prevent typos."""

        class StrictView(View):
            existing_attr = True

        # Valid
        StrictView.as_view(existing_attr=False)

        # Invalid
        with pytest.raises(TypeError) as excinfo:
            StrictView.as_view(non_existent_attr=123)
        assert "received an invalid keyword" in str(excinfo.value)


class TestFastAPIIntegration:
    """Integration tests verifying View behavior within a live FastAPI app."""

    def test_simple_get_request(self, app: FastAPI, client: TestClient):
        """Requirement: Standard GET requests work and return Response objects."""

        class HelloWorldView(View):
            async def get(self) -> Response:
                return Response("Hello World")

        app.add_api_route("/hello", HelloWorldView.as_view())
        response = client.get("/hello")
        assert response.status_code == 200
        assert response.text == "Hello World"

    def test_dispatch_method_not_allowed(self, app: FastAPI, client: TestClient):
        """Requirement: Returns 405 if the HTTP method is not implemented in
        the class."""

        class ReadOnlyView(View):
            async def get(self) -> Response:
                return Response("OK")

        # Register GET and POST, but view only implements get()
        app.add_api_route("/read-only", ReadOnlyView.as_view(), methods=["GET", "POST"])

        response = client.post("/read-only")
        assert response.status_code == 405
        assert "Method Not Allowed" in response.text

    def test_request_and_kwargs_access(self, app: FastAPI, client: TestClient):
        """Requirement: self.request and self.kwargs are correctly populated."""

        class ContextView(View):
            async def get(self):
                # self.kwargs merges path params and extra logic
                pk = self.kwargs.get("pk")
                method = self.request.method
                return Response(f"{method} item {pk}")

        app.add_api_route("/item/{pk}", ContextView.as_view())
        response = client.get("/item/123")
        assert response.text == "GET item 123"

    def test_dependency_injection(self, app: FastAPI, client: TestClient):
        """Requirement: signature copying logic preserves FastAPI's Depends()."""

        def get_token(request: Request):
            return request.headers.get("X-Token")

        class AuthView(View):
            async def get(self, token: str | None = Depends(get_token)):
                return Response(f"Token: {token}")

        app.add_api_route("/auth", AuthView.as_view())
        response = client.get("/auth", headers={"X-Token": "secret-123"})
        assert response.text == "Token: secret-123"

    def test_path_parameters_validation(self, app: FastAPI, client: TestClient):
        """Requirement: FastAPI type hints for path params are enforced."""

        class NumericView(View):
            async def get(self, val: int):
                return Response(f"Value: {val}")

        app.add_api_route("/numeric/{val}", NumericView.as_view())

        # Valid integer
        assert client.get("/numeric/50").status_code == 200
        # Invalid string (triggers FastAPI Pydantic validation)
        assert client.get("/numeric/hello").status_code == 422

    def test_multiple_dependencies(self, app: FastAPI, client: TestClient):
        """Requirement: Handles multiple injected dependencies in one handler."""

        def dep_a():
            return "A"

        def dep_b():
            return "B"

        class MultiView(View):
            async def get(self, a: str = Depends(dep_a), b: str = Depends(dep_b)):
                return Response(f"{a}{b}")

        app.add_api_route("/multi", MultiView.as_view())
        assert client.get("/multi").text == "AB"

    def test_injected_dependency_not_passed_to_handler(
        self,
        app: FastAPI,
        client: TestClient,
    ):
        """Requirement: Injected-only params do not leak into handlers."""

        def dep_value():
            return "injected"

        class InjectedMixin:
            @classmethod
            def resolve_dependencies(cls, params, **kwargs):
                params.insert(
                    0,
                    inspect.Parameter(
                        name="injected",
                        kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=str,
                        default=Depends(dep_value),
                    ),
                )
                super().resolve_dependencies(params, **kwargs)

        class InjectedView(InjectedMixin, View):
            async def get(self):
                return Response("OK")

        app.add_api_route("/injected", InjectedView.as_view())
        assert client.get("/injected").text == "OK"

    def test_view_isolation_safety(self, app: FastAPI, client: TestClient):
        """Requirement: Requests do not share state (thread/instance safety)."""

        class StateView(View):
            hit_count = 0

            async def get(self):
                self.hit_count += 1
                return Response(str(self.hit_count))

        app.add_api_route("/state", StateView.as_view())

        # Every request must get a fresh instance
        assert client.get("/state").text == "1"
        assert client.get("/state").text == "1"

    def test_sync_handler_support(self, app: FastAPI, client: TestClient):
        """Requirement: Standard 'def' handlers work (run in threadpool)."""

        class SyncView(View):
            def get(self) -> Response:
                return Response("Sync handled")

        app.add_api_route("/sync", SyncView.as_view())
        assert client.get("/sync").text == "Sync handled"

    def test_json_automatic_conversion(self, app: FastAPI, client: TestClient):
        """Requirement: Handlers can return dicts for automatic JSON conversion."""

        class DataView(View):
            async def get(self):
                return {"success": True}

        app.add_api_route("/json", DataView.as_view())
        response = client.get("/json")
        assert response.json() == {"success": True}
        assert response.headers["content-type"] == "application/json"

    def test_initkwargs_persistence(self, app: FastAPI, client: TestClient):
        """Requirement: Attributes set in as_view() are available in handlers."""

        class ConfigView(View):
            template_mode: str = "default"

            async def get(self):
                return Response(self.template_mode)

        app.add_api_route("/v1", ConfigView.as_view(template_mode="legacy"))
        app.add_api_route("/v2", ConfigView.as_view(template_mode="modern"))

        assert client.get("/v1").text == "legacy"
        assert client.get("/v2").text == "modern"
