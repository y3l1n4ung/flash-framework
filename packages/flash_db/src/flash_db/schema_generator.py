from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Dict, Generic, TypeAlias, TypeVar, Union, cast

from pydantic import BaseModel, ConfigDict, Field, create_model
from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    inspect,
)
from sqlalchemy.orm import ColumnProperty, DeclarativeBase

T = TypeVar("T", bound=DeclarativeBase)
FieldMap: TypeAlias = Dict[str, Any]

SQL_TO_PYTHON_TYPE: dict[Any, type[Any]] = {
    String: str,
    Text: str,
    Integer: int,
    Float: float,
    Numeric: float,
    Boolean: bool,
    DateTime: datetime,
    Date: date,
    Time: time,
    JSON: dict,
    ARRAY: list,
}


@dataclass(slots=True, frozen=True)
class SchemaConfig:
    """Configuration for schema generation filtering."""

    exclude: set[str] = field(default_factory=set)
    readonly_fields: set[str] = field(
        default_factory=lambda: {"id", "created_at", "updated_at"},
    )
    sensitive_fields: set[str] = field(
        default_factory=lambda: {"password", "secret", "salt", "hash"},
    )

    create_fields: set[str] | None = None
    update_fields: set[str] | None = None


class SchemaGenerator(Generic[T]):
    """
    Generates Pydantic schemas from SQLAlchemy models.

    Example:
        >>> config = SchemaConfig(readonly_fields={'id', 'created_at'})
        >>> generator = SchemaGenerator(User, config)
        >>> UserCreate = generator.create_schema()
        >>> UserResponse = generator.response_schema()
    """

    def __init__(self, model_class: type[T], config: SchemaConfig | None = None):
        self.model_class = model_class
        self.config = config or SchemaConfig()
        self.inspector = inspect(model_class)
        self._columns: Iterable[Column[Any]] = list(self._get_model_columns())

    @staticmethod
    def _get_python_type(column: Column[Any]) -> Any:
        """Resolves SQLAlchemy column type to Python type."""
        for sql_type, py_type in SQL_TO_PYTHON_TYPE.items():
            if isinstance(column.type, sql_type):
                return py_type
        return None

    def _get_model_columns(self) -> Iterable[Column[Any]]:
        """Helper to iterate only over actual column attributes of the model."""
        for attr in self.inspector.attrs:
            if isinstance(attr, ColumnProperty):
                yield cast("Column[Any]", attr.columns[0])

    @staticmethod
    def _has_default(column: Column[Any]) -> bool:
        """Checks if a column has any form of default or auto-update value."""
        return any(
            [
                column.default is not None,
                column.server_default is not None,
                column.onupdate is not None,
                column.server_onupdate is not None,
            ],
        )

    def create_schema(self) -> type[BaseModel]:
        """
        Generates a schema for resource creation (POST).
        Automatically excludes primary keys and fields with defaults.

        """
        fields: FieldMap = {}
        exclude = self.config.exclude | self.config.readonly_fields

        for column in self._columns:
            name = column.name

            if self.config.create_fields is not None:
                if name not in self.config.create_fields or name in exclude:
                    continue
            elif name in exclude or column.primary_key:
                continue

            py_type = self._get_python_type(column)

            if column.nullable:
                fields[name] = (
                    Union[py_type, None],
                    Field(default=None, description=column.comment),
                )
            else:
                fields[name] = (py_type, Field(description=column.comment))

        return create_model(
            self.model_class.__name__ + "Create",
            __config__=ConfigDict(
                from_attributes=True,
            ),
            **fields,
        )

    def update_schema(self) -> type[BaseModel]:
        """
        Generates a schema for partial updates (PATCH).
        All fields are made optional/nullable.
        """
        fields: FieldMap = {}
        exclude = self.config.exclude | self.config.readonly_fields

        for column in self._columns:
            name = column.name

            if self.config.update_fields is not None:
                if name not in self.config.update_fields or name in exclude:
                    continue
            elif name in exclude or column.primary_key or column.onupdate:
                continue

            py_type = self._get_python_type(column)
            fields[name] = (
                Union[py_type, None],
                Field(default=None, description=column.comment),
            )

        return create_model(
            self.model_class.__name__ + "Update",
            __config__=ConfigDict(
                from_attributes=True,
            ),
            **fields,
        )

    def response_schema(self) -> type[BaseModel]:
        """
        Generates a schema for data serialization (GET) with sensitive field filtering.
        """
        fields: FieldMap = {}

        for column in self._columns:
            name = column.name
            is_sensitive = any(s in name.lower() for s in self.config.sensitive_fields)
            if is_sensitive:
                # TODO add warning
                pass
            if name in self.config.exclude or is_sensitive:
                continue
            py_type = self._get_python_type(column)
            if column.nullable:
                fields[name] = (
                    Union[py_type, None],
                    Field(default=None, description=column.comment),
                )
            else:
                fields[name] = (py_type, Field(description=column.comment))

        return create_model(
            self.model_class.__name__ + "Response",
            __config__=ConfigDict(
                from_attributes=True,
            ),
            **fields,
        )
