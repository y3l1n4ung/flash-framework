import pytest
from flash_html.forms import (
    BaseForm,
    BooleanField,
    CharField,
    ChoiceField,
    EmailField,
    IntegerField,
    TextAreaField,
    URLField,
    ValidationError,
)
from pydantic import BaseModel
from pydantic import Field as PydanticField
from starlette.requests import Request


class TestBasicFormValidation:
    def test_required_field(self):
        class RequiredForm(BaseForm):
            name = CharField(required=True)

        form = RequiredForm(data={})
        assert form.is_valid() is False
        assert form.errors["name"] == ["This field is required."]

    def test_min_max_length(self):
        class LengthForm(BaseForm):
            name = CharField(min_length=2, max_length=4)

        form = LengthForm(data={"name": "a"})
        assert form.is_valid() is False
        assert "at least 2 characters" in form.errors["name"][0]

        form = LengthForm(data={"name": "abcde"})
        assert form.is_valid() is False
        assert "at most 4 characters" in form.errors["name"][0]

        form = LengthForm(data={"name": "abcd"})
        assert form.is_valid() is True

    def test_choice_field(self):
        class ChoiceForm(BaseForm):
            status = ChoiceField(choices=[("a", "A"), ("b", "B")])

        form = ChoiceForm(data={"status": "c"})
        assert form.is_valid() is False
        assert form.errors["status"] == ["Select a valid choice."]

        form = ChoiceForm(data={"status": "a"})
        assert form.is_valid() is True

    def test_integer_field_bounds(self):
        class IntForm(BaseForm):
            count = IntegerField(min_value=1, max_value=3)

        form = IntForm(data={"count": "0"})
        assert form.is_valid() is False
        assert "greater than or equal to 1" in form.errors["count"][0]

        form = IntForm(data={"count": "4"})
        assert form.is_valid() is False
        assert "less than or equal to 3" in form.errors["count"][0]

        form = IntForm(data={"count": "2"})
        assert form.is_valid() is True

    def test_boolean_field_required(self):
        class FlagForm(BaseForm):
            accepted = BooleanField(required=True)

        form = FlagForm(data={"accepted": "on"})
        assert form.is_valid() is True
        assert form.cleaned_data["accepted"] is True

        form = FlagForm(data={"accepted": ""})
        assert form.is_valid() is False
        assert form.errors["accepted"] == ["This field is required."]

    def test_initial_is_used_when_data_missing(self):
        class InitialForm(BaseForm):
            name = CharField(initial="default")

        form = InitialForm()
        assert form.is_valid() is True
        assert form.cleaned_data["name"] == "default"


class TestFormCleanAndErrors:
    def test_form_clean_adds_non_field_errors(self):
        class CleanForm(BaseForm):
            name = CharField(required=True)

            def clean(self):
                message = "Invalid combination."
                raise ValidationError(message)

        form = CleanForm(data={"name": "ok"})
        assert form.is_valid() is False
        assert form.non_field_errors == ["Invalid combination."]

    def test_add_error_for_specific_field(self):
        class CleanForm(BaseForm):
            name = CharField(required=True)

            def clean(self):
                self.add_error("name", "Custom error.")

        form = CleanForm(data={"name": "ok"})
        assert form.is_valid() is False
        assert form.errors["name"] == ["Custom error."]


class TestTemplateIntegration:
    def test_fields_property_includes_labels_values_errors(self):
        class FieldForm(BaseForm):
            first_name = CharField()

        form = FieldForm(data={"first_name": "Ada"})
        assert form.is_valid() is True

        fields = form.fields
        assert fields[0].name == "first_name"
        assert fields[0].label == "First Name"
        assert fields[0].value == "Ada"
        assert fields[0].errors == []

    def test_field_form_parameter_metadata(self):
        field = CharField(
            required=True,
            min_length=2,
            max_length=4,
            description="Name",
        )
        param = field.get_form_parameter()
        assert param.min_length == 2
        assert param.max_length == 4
        assert param.description == "Name"

    def test_bound_field_metadata(self):
        class MetaForm(BaseForm):
            bio = TextAreaField(
                placeholder="Write something",
                help_text="Tell us about yourself.",
                attrs={"rows": 5},
            )
            contact = EmailField()
            website = URLField(required=False)
            status = ChoiceField(choices=[("a", "A")])

        form = MetaForm(data={"bio": "Hi"})
        assert form.is_valid() is True
        fields = {field.name: field for field in form.fields}
        assert fields["bio"].input_type == "textarea"
        assert fields["bio"].placeholder == "Write something"
        assert fields["bio"].help_text == "Tell us about yourself."
        assert fields["bio"].attrs["rows"] == 5
        assert fields["status"].input_type == "select"


class TestPydanticIntegration:
    def test_pydantic_model_validation(self):
        class Payload(BaseModel):
            name: str = PydanticField(min_length=3)

        class PydanticForm(BaseForm):
            name = CharField(required=True)
            pydantic_model = Payload

        form = PydanticForm(data={"name": "ab"})
        assert form.is_valid() is False
        assert "at least 3 characters" in form.errors["name"][0]

        form = PydanticForm(data={"name": "abcd"})
        assert form.is_valid() is True
        assert form.cleaned_data["name"] == "abcd"
        assert form.cleaned.name == "abcd"

    def test_auto_fields_from_pydantic_model(self):
        class Payload(BaseModel):
            title: str = PydanticField(min_length=2, max_length=5)
            published: bool = False
            count: int | None = PydanticField(default=None, ge=1, le=3)

        class AutoForm(BaseForm[Payload]):
            pydantic_model = Payload

        assert "title" in AutoForm.declared_fields
        assert "published" in AutoForm.declared_fields
        assert "count" in AutoForm.declared_fields

        form = AutoForm(data={"title": "okay", "published": "on", "count": "2"})
        assert form.is_valid() is True
        assert form.cleaned.title == "okay"


class TestDependencyIntegration:
    @pytest.mark.asyncio
    async def test_as_dependency_binds_data(self):
        class DepForm(BaseForm):
            name = CharField(required=True)

        async def receive():
            return {
                "type": "http.request",
                "body": b"name=ada",
                "more_body": False,
            }

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
            },
            receive,
        )

        dependency = DepForm.as_dependency()
        form = await dependency(request)

        assert isinstance(form, DepForm)
        assert form.is_valid() is True
        assert form.cleaned_data["name"] == "ada"

    def test_as_form_dependency(self):
        class DepForm(BaseForm):
            name = CharField(required=True)

        request = Request({"type": "http", "method": "POST"})
        dependency = DepForm.as_form()
        form = dependency(request, name="ada")

        assert isinstance(form, DepForm)
        assert form.is_valid() is True
        assert form.cleaned_data["name"] == "ada"
