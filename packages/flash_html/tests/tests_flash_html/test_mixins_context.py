import pytest
from flash_html.views.mixins.context import ContextMixin
from pydantic import BaseModel


class TestContextMixin:
    """Test suite for the ContextMixin logic."""

    def test_view_injection(self):
        """
        Requirement: The 'view' instance is automatically injected into the context.
        This allows templates to access view attributes/methods
        (e.g., {{ view.some_helper() }}).
        """
        mixin = ContextMixin()
        ctx = mixin.get_context_data()
        assert ctx["view"] is mixin

    def test_kwargs_merge(self):
        """
        Requirement: Keyword arguments passed to get_context_data are included in the
        result.
        """
        mixin = ContextMixin()
        ctx = mixin.get_context_data(foo="bar", num=1)
        assert ctx["foo"] == "bar"
        assert ctx["num"] == 1

    def test_extra_context_dict(self):
        """
        Requirement: 'extra_context' defined as a dictionary is merged into the context.
        """

        class DictView(ContextMixin):
            extra_context = {"static_key": "static_value"}

        view = DictView()
        ctx = view.get_context_data(dynamic_key="dynamic_value")

        assert ctx["static_key"] == "static_value"
        assert ctx["dynamic_key"] == "dynamic_value"

    def test_extra_context_pydantic(self):
        """
        Requirement: 'extra_context' defined as a Pydantic model is converted to a
        dict and merged.
        """

        class PageConfig(BaseModel):
            title: str
            show_sidebar: bool

        class PydanticView(ContextMixin):
            extra_context = PageConfig(title="Test Page", show_sidebar=True)

        view = PydanticView()
        ctx = view.get_context_data()

        assert ctx["title"] == "Test Page"
        assert ctx["show_sidebar"] is True

    def test_priority_logic(self):
        """
        Requirement: 'extra_context' overrides arguments passed via kwargs.
        This ensures class-level definitions take precedence over dynamic
        defaults if conflict occurs.
        """

        class OverrideView(ContextMixin):
            extra_context = {"theme": "dark"}

        view = OverrideView()
        # "theme" passed in kwargs should be overwritten by class-level extra_context
        ctx = view.get_context_data(theme="light", other="keep")

        assert ctx["theme"] == "dark"
        assert ctx["other"] == "keep"

    def test_invalid_extra_context_type(self):
        """
        Requirement: Raises TypeError if extra_context is not a dict or
        Pydantic BaseModel.
        """

        class BrokenView(ContextMixin):
            extra_context = "not a dict or model"  # type: ignore

        view = BrokenView()
        with pytest.raises(TypeError) as excinfo:
            view.get_context_data()

        assert "must be a dict or Pydantic BaseModel" in str(excinfo.value)

    def test_generic_type_usage(self):
        """
        Requirement: Generics syntax works at runtime without error.
        (This confirms compatibility with the Generic[ExtraContextT] definition).
        """

        class Config(BaseModel):
            id: int

        class TypedView(ContextMixin[Config]):
            extra_context = Config(id=99)

        view = TypedView()
        ctx = view.get_context_data()
        assert ctx["id"] == 99

    def test_no_side_effects_on_kwargs(self):
        """
        Requirement: get_context_data should not mutate the input kwargs dictionary.
        """
        mixin = ContextMixin()
        input_kwargs = {"key": "original"}

        # Call method
        ctx = mixin.get_context_data(**input_kwargs)

        # Ensure 'view' was added to the result...
        assert "view" in ctx
        # ...but NOT to the original dictionary
        assert "view" not in input_kwargs
