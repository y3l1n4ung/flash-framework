import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from flash_html.forms import BaseForm, CharField
from flash_html.template_manager import TemplateManager
from flash_html.views.forms import FormView


class SimpleForm(BaseForm):
    name = CharField(required=True)


def build_app(tmp_path) -> TestClient:
    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir(parents=True, exist_ok=True)
    (tpl_dir / "form.html").write_text(
        "{{ form.fields[0].name }}|{{ form.fields[0].value }}|"
        "{{ form.errors.get('name') }}"
    )

    app = FastAPI()
    app.state.template_manager = TemplateManager(project_root=tmp_path)

    class SimpleFormView(FormView):
        template_name = "form.html"
        form_class = SimpleForm
        success_url = "/ok"

    app.add_api_route("/form", SimpleFormView.as_view(), methods=["GET", "POST"])
    return TestClient(app)


class TestFormView:
    def test_get_renders_form(self, tmp_path):
        client = build_app(tmp_path)
        response = client.get("/form")
        assert response.status_code == 200
        assert "name|" in response.text
        assert "This field is required." not in response.text

    def test_post_invalid_renders_errors(self, tmp_path):
        client = build_app(tmp_path)
        response = client.post("/form", data={})
        assert response.status_code == 200
        assert "This field is required." in response.text

    def test_post_valid_redirects(self, tmp_path):
        client = build_app(tmp_path)
        response = client.post("/form", data={"name": "Ada"}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/ok"

    def test_missing_success_url_raises(self):
        class MissingSuccessView(FormView):
            template_name = "form.html"
            form_class = SimpleForm
            success_url = None

        view = MissingSuccessView()
        with pytest.raises(RuntimeError):
            view.get_success_url()
