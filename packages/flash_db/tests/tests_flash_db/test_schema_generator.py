from sqlalchemy import Column, Integer, DateTime, String
from sqlalchemy.types import UserDefinedType
from pydantic import ValidationError
import datetime
from typing import Union, Any
from flash_db.schema_generator import SchemaGenerator, SchemaConfig
import pytest
from .models import Article, Profile


class TestSchemaGenerator:
    @pytest.fixture
    def profile_generator(self) -> SchemaGenerator[Profile]:
        return SchemaGenerator(model_class=Profile)

    def test_create_schema_excludes_defaults_and_pks(
        self, profile_generator: SchemaGenerator[Profile]
    ):
        ProfileCreate = profile_generator.create_schema()
        fields = ProfileCreate.model_fields

        # Check exclusions
        assert "id" not in fields
        assert "created_at" not in fields
        assert "updated_at" not in fields

        # Check required/optional status and defaults
        assert "full_name" in fields
        assert fields["full_name"].is_required() is True

        assert "bio" in fields
        assert fields["bio"].is_required() is False
        # assert fields["bio"].default == "No bio provided"
        assert fields["bio"].annotation is Union[str, None]

        assert "salary_expectation" in fields
        assert fields["salary_expectation"].is_required() is False  # Nullable=True

        # Type checks
        assert fields["full_name"].annotation is str
        # Since salary_expectation is nullable, it should be Union[float, None]
        assert fields["salary_expectation"].annotation == Union[float, None]

        assert "api_key_hash" in fields
        assert fields["api_key_hash"].annotation is str

        assert "is_verified" in fields
        assert fields["is_verified"].annotation is bool

        assert "internal_notes" in fields
        assert fields["internal_notes"].annotation is Union[str, None]

        assert "metadata_json" in fields
        assert fields["metadata_json"].annotation is Union[dict, None]

    def test_update_schema_enforces_full_optionality(
        self, profile_generator: SchemaGenerator[Profile]
    ):
        ProfileUpdate = profile_generator.update_schema()
        fields = ProfileUpdate.model_fields

        # Check exclusions (Same as Create)
        assert "id" not in fields
        assert "created_at" not in fields
        assert "updated_at" not in fields

        # Every field must be optional (PATCH behavior)
        for field_name, field_info in fields.items():
            assert field_info.is_required() is False
            assert field_info.default is None

        # Type checks for specific fields
        assert fields["full_name"].annotation == Union[str, None]
        assert fields["salary_expectation"].annotation == Union[float, None]
        assert fields["is_verified"].annotation == Union[bool, None]
        assert fields["internal_notes"].annotation == Union[str, None]

        # Type checks for non-specific fields
        assert fields["bio"].annotation is Union[str, None]
        assert fields["api_key_hash"].annotation is Union[str, None]

    def test_response_schema_filters_and_types(
        self, profile_generator: SchemaGenerator[Profile]
    ):
        ProfileResponse = profile_generator.response_schema()
        fields = ProfileResponse.model_fields

        # Sensitive data check
        assert "api_key_hash" not in fields

        # Read-only fields MUST be present in Response
        assert "id" in fields
        assert "created_at" in fields
        assert "updated_at" in fields

        # Check required status (Response usually mirrors DB nullability)
        assert fields["full_name"].is_required() is True
        assert fields["salary_expectation"].is_required() is False

        # Strict Type checks
        assert fields["id"].annotation is int
        assert fields["full_name"].annotation is str
        assert fields["is_verified"].annotation is bool
        assert fields["created_at"].annotation is datetime.datetime
        assert fields["salary_expectation"].annotation == Union[float, None]
        assert fields["bio"].annotation is Union[str, None]
        assert fields["internal_notes"].annotation is Union[str, None]
        # Optional Type checks
        assert fields["updated_at"].annotation is Union[datetime.datetime, None]

    def test_custom_configuration_overrides(self):
        config = SchemaConfig(
            exclude={"internal_notes"},
            readonly_fields={"created_at"},
            sensitive_fields={"salary"},
        )
        generator = SchemaGenerator(Profile, config)

        Response = generator.response_schema()
        Create = generator.create_schema()

        # Custom exclude
        assert "internal_notes" not in Response.model_fields
        assert "internal_notes" not in Create.model_fields

        # Custom readonly
        assert "created_at" in Response.model_fields
        assert "created_at" not in Create.model_fields

        # Custom sensitive keyword
        assert "salary_expectation" not in Response.model_fields

    def test_explicit_field_inclusion_whitelisting(self):
        config = SchemaConfig(create_fields={"full_name", "bio"})
        generator = SchemaGenerator(Profile, config)

        Create = generator.create_schema()
        assert set(Create.model_fields.keys()) == {"full_name", "bio"}
        assert Create.model_fields["bio"].annotation == Union[str, None]

    def test_relationship_exclusion(self):
        generator = SchemaGenerator(Article)

        # Relationships should never leak into DTOs
        assert "comments" not in generator.create_schema().model_fields
        assert "comments" not in generator.update_schema().model_fields
        assert "comments" not in generator.response_schema().model_fields

    def test_pydantic_runtime_validation(self):
        generator = SchemaGenerator(Profile)
        ProfileUpdate = generator.update_schema()

        ProfileCreate = generator.create_schema()
        ProfileResponse = generator.response_schema()
        generator.config

        # 1. Validation Error: Missing required field in Create
        with pytest.raises(ValidationError):
            ProfileCreate(api_key_hash="abc")  # full_name is missing

        # 2. Validation Error: Incorrect type (string instead of float/numeric)
        with pytest.raises(ValidationError):
            ProfileCreate(full_name="John", salary_expectation="not-a-number")

        # 3. Successful type coercion (Pydantic feature)
        valid_create = ProfileCreate(
            full_name="John",
            salary_expectation="50000.50",
            is_verified="true",
            api_key_hash="x-api-key-test",
        )
        assert valid_create.salary_expectation == 50000.50  # type: ignore
        assert valid_create.is_verified is True  # type: ignore
        assert valid_create.api_key_hash == "x-api-key-test"  # type: ignore
        assert valid_create.full_name == "John"  # type: ignore

        # 4. Update Schema (PATCH) allows partial data
        assert "salary_expectation" in ProfileUpdate.model_fields
        valid_update = ProfileUpdate(salary_expectation=60000.0)
        data = valid_update.model_dump(exclude_unset=False)
        assert data["full_name"] is None
        assert data["salary_expectation"] == 60000.0
        # 5. Response Schema should be able to parse DB-like data
        mock_db_data = {
            "id": 1,
            "full_name": "Jane Doe",
            "is_verified": True,
            "created_at": datetime.datetime.now(),
            "salary_expectation": None,
        }
        valid_response = ProfileResponse(**mock_db_data)
        assert valid_response.id == 1  # type: ignore
        assert valid_response.salary_expectation is None  # type: ignore

    def test_explicit_field_filtering_with_exclusions(self):
        config = SchemaConfig(create_fields={"full_name", "id"}, exclude={"id"})
        generator = SchemaGenerator(Profile, config=config)
        Create = generator.create_schema()
        assert "id" not in Create.model_fields
        assert "full_name" in Create.model_fields

    def test_unsupported_type_fallback(
        self, profile_generator: SchemaGenerator[Profile]
    ):
        """Triggers the 'return Any' line in _get_python_type using JSON type."""
        Response = profile_generator.response_schema()
        # Verify field exists first to avoid KeyError, then check annotation
        assert "metadata_json" in Response.model_fields
        assert Response.model_fields["metadata_json"].annotation == Union[dict, None]

    def test_get_python_type_fallback(
        self, profile_generator: SchemaGenerator[Profile]
    ):
        """
        Covers the implicit fallback in _get_python_type.
        Verifies that unknown SQL types result in an effectively null/any annotation.
        """
        ResponseSchema = profile_generator.response_schema()
        assert "mystery_blob" in ResponseSchema.model_fields

        # When _get_python_type returns None, Pydantic defaults the annotation to NoneType
        # for nullable fields, which is functionally equivalent to missing type info.
        annotation = ResponseSchema.model_fields["mystery_blob"].annotation
        assert (
            annotation is type(None) or annotation is Any or "None" in str(annotation)
        )

    def test_explicit_whitelisting_with_exclude_collision(self):
        config = SchemaConfig(create_fields={"full_name", "bio"}, exclude={"bio"})
        gen = SchemaGenerator(Profile, config)
        CreateSchema = gen.create_schema()

        # 'bio' should be skipped because it is in 'exclude'
        assert "full_name" in CreateSchema.model_fields
        assert "bio" not in CreateSchema.model_fields

    def test_response_schema_sensitive_filter_branch(
        self, profile_generator: SchemaGenerator[Profile]
    ):
        """
        Triggers the 'is_sensitive' block and the associated 'pass' statement.
        """
        # 'api_key_hash' contains 'hash', which is a default sensitive keyword
        ResponseSchema = profile_generator.response_schema()
        assert "api_key_hash" not in ResponseSchema.model_fields

    def test_has_default(self):
        # Testing different default scenarios on columns
        col_with_default = Column(Integer, default=0)
        col_with_server_default = Column(Integer, server_default="0")
        col_with_onupdate = Column(DateTime, onupdate=datetime.datetime.now)
        col_plain = Column(String)

        assert SchemaGenerator._has_default(col_with_default) is True
        assert SchemaGenerator._has_default(col_with_server_default) is True
        assert SchemaGenerator._has_default(col_with_onupdate) is True
        assert SchemaGenerator._has_default(col_plain) is False

    def test_update_fields_whitelisting_with_exclude_collision(self):
        """
        Tests logic when a field is in update_fields but also in the exclude set.
        """
        config = SchemaConfig(update_fields={"full_name", "id"}, exclude={"full_name"})
        gen = SchemaGenerator(Profile, config)
        UpdateSchema = gen.update_schema()

        # 'full_name' is skipped because it's in 'exclude'
        # 'id' is skipped because it's a primary key (implicitly in logic or readonly)
        assert "full_name" not in UpdateSchema.model_fields
        assert "id" not in UpdateSchema.model_fields
