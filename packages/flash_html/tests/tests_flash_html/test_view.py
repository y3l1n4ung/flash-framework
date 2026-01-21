import pytest
from fastapi import FastAPI, Request, Response, Depends
from fastapi.testclient import TestClient
from flash_html.views.base import View


class MockRequest:
    def __init__(self, method: str = "GET"):
        self.method = method


class TestViewBase:
    """Test suite for the Base View logic (Unit Tests)."""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """
        Requirement: View accepts kwargs in __init__ and sets them as attributes.
        """
        view = View(key="value", number=42)
        assert getattr(view, "key") == "value"
        assert getattr(view, "number") == 42

    @pytest.mark.asyncio
    async def test_dispatch_get_method(self):
        """
        Requirement: dispatch() routes GET requests to the get() method.
        """

        class SimpleView(View):
            async def get(self, request: Request) -> Response:
                return Response("GET Handled")

        endpoint = SimpleView.as_view()
        request = MockRequest(method="GET")

        # as_view returns a wrapper, calling it triggers dispatch
        response = await endpoint(request)  # type: ignore
        assert response.body == b"GET Handled"

    @pytest.mark.asyncio
    async def test_dispatch_method_not_allowed(self):
        """
        Requirement: Dispatching a method not implemented (e.g. POST) returns 405.
        """

        class ReadOnlyView(View):
            async def get(self, request: Request) -> Response:
                return Response("OK")

        endpoint = ReadOnlyView.as_view()
        request = MockRequest(method="POST")

        response = await endpoint(request)  # type: ignore
        assert response.status_code == 405
        assert response.body == b"Method Not Allowed"

    @pytest.mark.asyncio
    async def test_dispatch_unknown_verb(self):
        """
        Requirement: Dispatching a completely unknown HTTP verb (e.g. TEAPOT) returns 405.
        """

        class AnyView(View):
            pass

        endpoint = AnyView.as_view()
        request = MockRequest(method="TEAPOT")

        response = await endpoint(request)  # type: ignore
        assert response.status_code == 405

    def test_as_view_strict_validation(self):
        """
        Requirement: as_view() should raise TypeError if passed an argument
        that is NOT an attribute of the class.
        """

        class StrictView(View):
            existing_attr = True

        # 1. Valid case
        StrictView.as_view(existing_attr=False)

        # 2. Invalid case
        with pytest.raises(TypeError) as excinfo:
            StrictView.as_view(non_existent_attr=123)

        assert "received an invalid keyword" in str(excinfo.value)
        assert "non_existent_attr" in str(excinfo.value)


class TestFastAPIIntegration:
    """
    Integration tests verifying that View works correctly within a FastAPI application.
    This ensures dependency injection, routing, and parameters work as expected.
    """

    @pytest.fixture
    def app(self):
        return FastAPI()

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_simple_get_request(self, app, client):
        class HelloWorldView(View):
            async def get(self, request: Request) -> Response:
                return Response("Hello World")

        app.add_api_route("/hello", HelloWorldView.as_view())

        response = client.get("/hello")
        assert response.status_code == 200
        assert response.text == "Hello World"

    def test_dependency_injection(self, app, client):
        """
        Requirement: FastAPI dependencies (Depends) works in class-based views.
        This relies on the signature copying magic in as_view().
        """

        def get_user_agent(request: Request):
            return request.headers.get("User-Agent")

        class UserAgentView(View):
            # Dependency injected into 'ua'
            async def get(
                self, request: Request, ua: str | None = Depends(get_user_agent)
            ):
                return Response(f"UA: {ua}")

        app.add_api_route("/ua", UserAgentView.as_view())

        response = client.get("/ua", headers={"User-Agent": "TestClient"})
        assert response.status_code == 200
        assert response.text == "UA: TestClient"

    def test_path_parameters(self, app, client):
        """
        Requirement: Path parameters declared in the method signature are extracted.
        """

        class ItemView(View):
            async def get(self, request: Request, item_id: int):
                return Response(f"Item: {item_id}")

        app.add_api_route("/items/{item_id}", ItemView.as_view())

        response = client.get("/items/42")
        assert response.status_code == 200
        assert response.text == "Item: 42"

        # Verify type validation (FastAPI feature)
        response = client.get("/items/not-a-number")
        assert response.status_code == 422  # Unprocessable Entity

    def test_query_parameters(self, app, client):
        """
        Requirement: Query parameters are extracted correctly.
        """

        class SearchView(View):
            async def get(self, request: Request, q: str = "default"):
                return Response(f"Search: {q}")

        app.add_api_route("/search", SearchView.as_view())

        # 1. With param
        response = client.get("/search?q=python")
        assert response.text == "Search: python"

        # 2. Without param (default)
        response = client.get("/search")
        assert response.text == "Search: default"

    def test_sync_handler_support(self, app, client):
        """
        Requirement: Synchronous methods (def get) are supported and run in threadpool.
        """

        class SyncView(View):
            def get(self, request: Request) -> Response:
                return Response("Sync Works")

        app.add_api_route("/sync", SyncView.as_view())

        response = client.get("/sync")
        assert response.status_code == 200
        assert response.text == "Sync Works"

    def test_multiple_methods_on_view(self, app, client):
        """
        Requirement: One view class can handle multiple verbs (GET, POST).
        Note: We must explicitly tell FastAPI which methods are allowed in add_api_route,
        otherwise it defaults to just GET unless the handler name implies otherwise,
        but since we wrap it in 'view', FastAPI sees one function.
        """

        class MultiView(View):
            async def get(self, request: Request):
                return Response("GET")

            async def post(self, request: Request):
                return Response("POST")

        # Explicitly register methods
        app.add_api_route("/multi", MultiView.as_view(), methods=["GET", "POST"])

        assert client.get("/multi").text == "GET"
        assert client.post("/multi").text == "POST"
        assert client.put("/multi").status_code == 405

    def test_initkwargs_configuration(self, app, client):
        """
        Requirement: as_view(param=value) overrides class attributes at runtime.
        """

        class TitleView(View):
            title: str = "Original"

            async def get(self, request: Request):
                return Response(self.title)

        app.add_api_route("/default", TitleView.as_view())
        app.add_api_route("/custom", TitleView.as_view(title="Customized"))

        assert client.get("/default").text == "Original"
        assert client.get("/custom").text == "Customized"
