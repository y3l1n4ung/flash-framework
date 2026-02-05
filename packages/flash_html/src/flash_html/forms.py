from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from enum import Enum
from types import UnionType
from typing import (
    Any,
    ClassVar,
    Generic,
    Literal,
    TypedDict,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
)

import annotated_types as at
from fastapi import Form, Request, UploadFile
from pydantic import AnyUrl, EmailStr
from pydantic import BaseModel as PydanticBaseModel
from pydantic import ValidationError as PydanticValidationError
from pydantic_core import PydanticUndefined


class ValidationError(ValueError):
    def __init__(self, message: str | list[str]) -> None:
        if isinstance(message, list):
            self.messages = message
            super().__init__("\n".join(message))
        else:
            self.messages = [message]
            super().__init__(message)


InputType = Literal[
    "text",
    "password",
    "email",
    "url",
    "number",
    "checkbox",
    "hidden",
    "textarea",
    "select",
]


class FormSchemaExtra(TypedDict, total=False):
    label: str
    placeholder: str
    help_text: str
    input_type: InputType
    widget: InputType
    attrs: dict[str, Any]
    choices: list[tuple[str, str]] | list[str]
    openapi_examples: dict[str, Any]
    deprecated: bool | str


def form_ui(
    *,
    label: str | None = None,
    placeholder: str | None = None,
    help_text: str | None = None,
    input_type: InputType | None = None,
    widget: InputType | None = None,
    attrs: dict[str, Any] | None = None,
    choices: list[tuple[str, str]] | list[str] | None = None,
    openapi_examples: dict[str, Any] | None = None,
    deprecated: bool | str | None = None,
) -> FormSchemaExtra:
    """
    Build typed schema extras for Form <-> Pydantic integration.

    Use this helper to avoid typos in ``input_type``/``widget`` values.
    """
    extra: FormSchemaExtra = {}
    if label is not None:
        extra["label"] = label
    if placeholder is not None:
        extra["placeholder"] = placeholder
    if help_text is not None:
        extra["help_text"] = help_text
    if input_type is not None:
        extra["input_type"] = input_type
    if widget is not None:
        extra["widget"] = widget
    if attrs is not None:
        extra["attrs"] = attrs
    if choices is not None:
        extra["choices"] = choices
    if openapi_examples is not None:
        extra["openapi_examples"] = openapi_examples
    if deprecated is not None:
        extra["deprecated"] = deprecated
    return extra


class Field:
    def __init__(
        self,
        *,
        required: bool = True,
        label: str | None = None,
        initial: Any | None = None,
        input_type: str | None = None,
        placeholder: str | None = None,
        help_text: str | None = None,
        max_length: int | None = None,
        min_length: int | None = None,
        choices: list[tuple[str, str]] | None = None,
        pattern: str | None = None,
        regex: str | None = None,
        description: str | None = None,
        example: Any | None = None,
        examples: list[Any] | None = None,
        openapi_examples: dict[str, Any] | None = None,
        deprecated: bool | str | None = None,
        form_kwargs: dict[str, Any] | None = None,
        attrs: dict[str, Any] | None = None,
    ) -> None:
        self.required = required
        self.label = label
        self.initial = initial
        self.input_type = input_type or "text"
        self.placeholder = placeholder
        self.help_text = help_text
        self.max_length = max_length
        self.min_length = min_length
        self.choices = choices
        self.pattern = pattern
        self.regex = regex
        self.description = description
        self.example = example
        self.examples = examples
        self.openapi_examples = openapi_examples
        self.deprecated = deprecated
        self.form_kwargs = form_kwargs or {}
        self.attrs = attrs or {}

    def to_python(self, value: Any) -> Any:
        return value

    def get_annotation(self) -> Any:
        return str

    def get_form_metadata(self) -> dict[str, Any]:
        description = self.description or self.help_text
        metadata: dict[str, Any] = {
            "min_length": self.min_length,
            "max_length": self.max_length,
            "pattern": self.pattern,
            "regex": self.regex,
            "description": description,
            "example": self.example,
            "examples": self.examples,
            "openapi_examples": self.openapi_examples,
            "deprecated": self.deprecated,
        }
        metadata.update(self.form_kwargs)
        return {key: value for key, value in metadata.items() if value is not None}

    def get_form_parameter(self):
        # We always use None as default for FastAPI dependency injection
        # so that GET requests don't fail with 422.
        # Field validation still happens inside form.is_valid().
        return Form(None, **self.get_form_metadata())

    def validate(self, value: Any) -> None:
        if self.required and (value is None or value == ""):
            message = "This field is required."
            raise ValidationError(message)

        if isinstance(value, str):
            if self.max_length is not None and len(value) > self.max_length:
                message = f"Ensure this value has at most {self.max_length} characters."
                raise ValidationError(message)
            if self.min_length is not None and len(value) < self.min_length:
                message = (
                    f"Ensure this value has at least {self.min_length} characters."
                )
                raise ValidationError(message)
            pattern = self.pattern or self.regex
            if pattern is not None and not re.match(pattern, value):
                message = "Enter a valid value."
                raise ValidationError(message)

        if self.choices is not None:
            if not self.required and (value is None or value == ""):
                return
            if value not in {key for key, _ in self.choices}:
                message = "Select a valid choice."
                raise ValidationError(message)

    def clean(self, value: Any) -> Any:
        value = self.to_python(value)
        self.validate(value)
        return value


class CharField(Field):
    def to_python(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)


class BooleanField(Field):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("input_type", "checkbox")
        super().__init__(**kwargs)

    def to_python(self, value: Any) -> bool:
        if value in (True, "true", "True", "1", 1, "on", "yes", "y"):
            return True
        if value in (False, "false", "False", "0", 0, "off", "no", "n", None, ""):
            return False
        return bool(value)

    def validate(self, value: Any) -> None:
        if self.required and value is False:
            message = "This field is required."
            raise ValidationError(message)

    def get_annotation(self) -> Any:
        return bool


class ChoiceField(Field):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("input_type", "select")
        super().__init__(**kwargs)

    def to_python(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)


class EmailField(CharField):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("input_type", "email")
        super().__init__(**kwargs)

    def get_annotation(self) -> Any:
        return EmailStr


class URLField(CharField):
    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("input_type", "url")
        super().__init__(**kwargs)

    def get_annotation(self) -> Any:
        return AnyUrl


class IntegerField(Field):
    def __init__(
        self,
        *,
        min_value: int | None = None,
        max_value: int | None = None,
        gt: int | None = None,
        lt: int | None = None,
        **kwargs: Any,
    ) -> None:
        self.min_value = min_value
        self.max_value = max_value
        self.gt = gt
        self.lt = lt
        kwargs.setdefault("input_type", "number")
        super().__init__(**kwargs)

    def to_python(self, value: Any) -> int | None:
        if value in ("", None):
            return None
        return int(value)

    def validate(self, value: Any) -> None:
        super().validate(value)
        if value is None:
            return
        if self.min_value is not None and value < self.min_value:
            message = f"Ensure this value is greater than or equal to {self.min_value}."
            raise ValidationError(message)
        if self.gt is not None and value <= self.gt:
            message = f"Ensure this value is greater than {self.gt}."
            raise ValidationError(message)
        if self.max_value is not None and value > self.max_value:
            message = f"Ensure this value is less than or equal to {self.max_value}."
            raise ValidationError(message)
        if self.lt is not None and value >= self.lt:
            message = f"Ensure this value is less than {self.lt}."
            raise ValidationError(message)

    def get_annotation(self) -> Any:
        return int

    def get_form_metadata(self) -> dict[str, Any]:
        metadata = super().get_form_metadata()
        if self.min_value is not None:
            metadata["ge"] = self.min_value
        if self.max_value is not None:
            metadata["le"] = self.max_value
        if self.gt is not None:
            metadata["gt"] = self.gt
        if self.lt is not None:
            metadata["lt"] = self.lt
        return metadata


class TextAreaField(CharField):
    def __init__(self, *, rows: int | None = None, **kwargs: Any) -> None:
        kwargs.setdefault("input_type", "textarea")
        super().__init__(**kwargs)
        if rows is not None:
            self.attrs["rows"] = rows


@dataclass
class BoundField:
    name: str
    label: str
    value: Any
    errors: list[str]
    input_type: str
    placeholder: str | None
    help_text: str | None
    choices: list[tuple[str, str]] | None
    attrs: dict[str, Any]


FormModelT = TypeVar("FormModelT", bound=PydanticBaseModel)


class BaseForm(Generic[FormModelT]):
    """
    Base class for HTML forms with FastAPI-friendly validation.

    Define form fields as class attributes and optionally attach a Pydantic
    model to get typed access via ``cleaned``.

    Examples:
        >>> from pydantic import BaseModel, Field
        >>> class ArticleSchema(BaseModel):
        ...     title: str = Field(min_length=3)
        ...     published: bool = False
        ...
        >>> class ArticleForm(BaseForm[ArticleSchema]):
        ...     pydantic_model = ArticleSchema
        ...     # Optional explicit fields override auto-generated ones.
        ...
        >>> form = ArticleForm(data={"title": "Hello", "published": "on"})
        >>> form.is_valid()
        True
        >>> form.cleaned.title
        'Hello'
    """

    declared_fields: ClassVar[dict[str, Field]] = {}
    pydantic_model: ClassVar[type[PydanticBaseModel] | None] = None
    auto_fields: ClassVar[bool] = True

    def __init_subclass__(cls) -> None:
        fields: dict[str, Field] = {}
        for base in reversed(cls.__mro__[1:]):
            fields.update(getattr(base, "declared_fields", {}))
        fields.update(
            {
                name: value
                for name, value in cls.__dict__.items()
                if isinstance(value, Field)
            }
        )
        if cls.pydantic_model is not None and cls.auto_fields:
            auto_fields = cls._build_fields_from_model(cls.pydantic_model)
            for name, field in auto_fields.items():
                fields.setdefault(name, field)
        cls.declared_fields = fields
        super().__init_subclass__()

    def __init__(
        self,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        initial: dict[str, Any] | None = None,
        request: Any | None = None,
    ) -> None:
        self.data = data or {}
        self.files = files or {}
        self.initial = initial or {}
        self.request = request
        self.cleaned_data: dict[str, Any] = {}
        self._errors: dict[str, list[str]] = {}
        self._validated_model: FormModelT | None = None

    @classmethod
    def _build_fields_from_model(
        cls, model: type[PydanticBaseModel]
    ) -> dict[str, Field]:
        fields: dict[str, Field] = {}
        for name, info in model.model_fields.items():
            fields[name] = cls._field_from_model_field(name, info)
        return fields

    @classmethod
    def _normalize_choices(
        cls, choices: list[Any] | tuple[Any, ...] | None
    ) -> list[tuple[str, str]] | None:
        if not choices:
            return None
        normalized: list[tuple[str, str]] = []
        for item in choices:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                normalized.append((str(item[0]), str(item[1])))
            else:
                normalized.append((str(item), str(item)))
        return normalized

    @classmethod
    def _unwrap_optional(cls, annotation: Any) -> Any:
        origin = get_origin(annotation)
        if origin in (Union, UnionType):
            args = [arg for arg in get_args(annotation) if arg is not type(None)]
            if len(args) == 1:
                return args[0]
        return annotation

    @classmethod
    def _field_from_model_field(cls, name: str, info: Any) -> Field:
        annotation = cls._unwrap_optional(info.annotation)
        metadata = list(info.metadata or [])
        min_length = max_length = None
        min_value = max_value = None
        gt = lt = None
        pattern = None

        for meta in metadata:
            if isinstance(meta, at.MinLen):
                min_length = meta.min_length
            elif isinstance(meta, at.MaxLen):
                max_length = meta.max_length
            elif isinstance(meta, at.Ge):
                min_value = meta.ge
            elif isinstance(meta, at.Le):
                max_value = meta.le
            elif isinstance(meta, at.Gt):
                gt = meta.gt
            elif isinstance(meta, at.Lt):
                lt = meta.lt
            elif hasattr(meta, "pattern") and meta.pattern:
                pattern = meta.pattern

        extra = info.json_schema_extra or {}
        if not isinstance(extra, dict):
            extra = {}

        label = extra.get("label") or info.title or name.replace("_", " ").title()
        placeholder = extra.get("placeholder")
        help_text = extra.get("help_text")
        input_type = extra.get("input_type") or extra.get("widget")
        attrs = extra.get("attrs") or {}
        choices = cls._normalize_choices(extra.get("choices"))

        field_kwargs: dict[str, Any] = {
            "required": info.is_required(),
            "label": label,
            "initial": None if info.default is PydanticUndefined else info.default,
            "placeholder": placeholder,
            "help_text": help_text,
            "description": info.description,
            "example": info.examples[0] if getattr(info, "examples", None) else None,
            "examples": getattr(info, "examples", None),
            "openapi_examples": extra.get("openapi_examples"),
            "deprecated": extra.get("deprecated"),
            "attrs": attrs,
            "pattern": pattern,
        }

        origin = get_origin(annotation)
        if origin is Literal:
            literal_values = get_args(annotation)
            choices = [(str(value), str(value)) for value in literal_values]

        if isinstance(annotation, type) and issubclass(annotation, Enum):
            choices = [(str(member.value), str(member.name)) for member in annotation]

        if choices is not None:
            field_kwargs["choices"] = choices
            return ChoiceField(**field_kwargs)

        if input_type == "checkbox":
            return BooleanField(**field_kwargs)

        if input_type == "textarea":
            field_kwargs.update(
                {
                    "min_length": min_length,
                    "max_length": max_length,
                }
            )
            return TextAreaField(**field_kwargs)

        if annotation is bool:
            return BooleanField(**field_kwargs)

        if annotation is int:
            field_kwargs.update(
                {
                    "min_value": min_value,
                    "max_value": max_value,
                    "gt": gt,
                    "lt": lt,
                }
            )
            return IntegerField(**field_kwargs)

        if annotation is EmailStr:
            field_kwargs.update(
                {
                    "min_length": min_length,
                    "max_length": max_length,
                }
            )
            return EmailField(**field_kwargs)

        if annotation is AnyUrl:
            field_kwargs.update(
                {
                    "min_length": min_length,
                    "max_length": max_length,
                }
            )
            return URLField(**field_kwargs)

        field_kwargs.update(
            {
                "min_length": min_length,
                "max_length": max_length,
                "input_type": input_type,
            }
        )
        return CharField(**field_kwargs)

    @classmethod
    def as_dependency(cls):
        async def _dependency(request: Request) -> "BaseForm":
            form_data = await request.form()
            data: dict[str, Any] = {}
            files: dict[str, Any] = {}

            for key, value in form_data.multi_items():
                if isinstance(value, UploadFile):
                    files[key] = value
                else:
                    data[key] = value

            return cls(
                data=data,
                files=files or None,
                request=request,
            )

        return _dependency

    @classmethod
    def as_form(cls):
        def _dependency(request: Request, **data: Any) -> "BaseForm":
            return cls(
                data=data,
                request=request,
            )

        parameters: list[inspect.Parameter] = [
            inspect.Parameter(
                name="request",
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Request,
            )
        ]

        for name, field in cls.declared_fields.items():
            annotation = field.get_annotation()
            default = field.get_form_parameter()
            parameters.append(
                inspect.Parameter(
                    name=name,
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=annotation,
                    default=default,
                )
            )

        cast("Any", _dependency).__signature__ = inspect.Signature(
            parameters=parameters
        )
        return _dependency

    @property
    def errors(self) -> dict[str, list[str]]:
        return self._errors

    @property
    def non_field_errors(self) -> list[str]:
        return self._errors.get("__all__", [])

    def add_error(self, field: str | None, message: str) -> None:
        key = field or "__all__"
        self._errors.setdefault(key, []).append(message)

    def is_valid(self) -> bool:
        self._errors = {}
        self.cleaned_data = {}
        self._validated_model = None

        for name, field in self.declared_fields.items():
            raw_value = self.data.get(name, self.initial.get(name, field.initial))
            try:
                self.cleaned_data[name] = field.clean(raw_value)
            except ValidationError as exc:
                for message in exc.messages:
                    self.add_error(name, message)

        if self._errors:
            return False

        try:
            cleaned = self.clean()
            if cleaned is not None:
                self.cleaned_data.update(cleaned)
        except ValidationError as exc:
            for message in exc.messages:
                self.add_error(None, message)

        if self.pydantic_model is not None and not self._errors:
            try:
                model = self.pydantic_model(**self.cleaned_data)
                self.cleaned_data = model.model_dump()
                self._validated_model = cast("FormModelT", model)
            except PydanticValidationError as exc:
                for error in exc.errors():
                    loc = error.get("loc", ())
                    field = str(loc[0]) if loc else None
                    message = error.get("msg", "Invalid value.")
                    self.add_error(field, message)

        return not self._errors

    def clean(self) -> dict[str, Any] | None:
        return None

    @property
    def cleaned(self) -> FormModelT:
        if self.pydantic_model is None:
            msg = (
                f"{self.__class__.__name__} does not define pydantic_model; "
                "use cleaned_data instead."
            )
            raise RuntimeError(msg)
        if self._validated_model is None:
            msg = "Call is_valid() before accessing cleaned."
            raise RuntimeError(msg)
        return self._validated_model

    @property
    def fields(self) -> list[BoundField]:
        bound_fields: list[BoundField] = []
        for name, field in self.declared_fields.items():
            label = field.label or name.replace("_", " ").title()
            value = self.cleaned_data.get(
                name, self.data.get(name, self.initial.get(name, field.initial))
            )
            errors = self._errors.get(name, [])
            bound_fields.append(
                BoundField(
                    name=name,
                    label=label,
                    value=value,
                    errors=errors,
                    input_type=field.input_type,
                    placeholder=field.placeholder,
                    help_text=field.help_text,
                    choices=field.choices,
                    attrs=field.attrs,
                )
            )
        return bound_fields
