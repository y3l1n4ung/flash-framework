from datetime import datetime

import pytest
from flash_authentication.schemas import BaseUserSchema, UserCreateSchema
from pydantic import ValidationError


class TestUserCreateSchema:
    """
    Tests for UserCreate Pydantic model validation.
    """

    def test_valid_user_create(self):
        """Test happy path for user creation."""
        payload = {
            "username": "valid_user",
            "email": "test@example.com",
            "password": "StrongPassword1",
            "password_confirm": "StrongPassword1",
        }
        schema = UserCreateSchema(**payload)
        assert schema.username == "valid_user"
        assert schema.email == "test@example.com"

    def test_password_mismatch(self):
        """Test that validation fails if passwords do not match."""
        payload = {
            "username": "user",
            "email": "test@example.com",
            "password": "Password1",
            "password_confirm": "Password2",
        }
        with pytest.raises(ValidationError) as exc:
            UserCreateSchema(**payload)

        errors = exc.value.errors()
        assert any("Passwords do not match" in e["msg"] for e in errors)

    def test_username_validation_regex(self):
        """Test strict username characters (alphanumeric + underscore/hyphen)."""
        invalid_usernames = ["user space", "user@mail", "user!name"]

        for name in invalid_usernames:
            payload = {
                "username": name,
                "email": "test@example.com",
                "password": "Password1",
                "password_confirm": "Password1",
            }
            with pytest.raises(ValidationError) as exc:
                UserCreateSchema(**payload)
            # Check for Pydantic's pattern error
            assert "string_pattern_mismatch" in str(exc.value) or "pattern" in str(
                exc.value
            )

    def test_password_complexity_rules(self):
        """Test password complexity requirements (number + uppercase)."""
        # Case 1: No Number
        with pytest.raises(ValidationError) as exc_num:
            UserCreateSchema(
                username="user",
                email="a@b.com",
                password="Password",
                password_confirm="Password",
            )
        assert "at least one number" in str(exc_num.value)

        # Case 2: No Uppercase
        with pytest.raises(ValidationError) as exc_upper:
            UserCreateSchema(
                username="user",
                email="a@b.com",
                password="password1",
                password_confirm="password1",
            )
        assert "at least one uppercase" in str(exc_upper.value)

    def test_username_length_constraints(self):
        with pytest.raises(ValidationError) as exc_short:
            UserCreateSchema(
                username="ab", email="a@b.com", password="P1", password_confirm="P1"
            )
        assert "at least 3 characters" in str(exc_short.value)

        # Too long (>150)
        with pytest.raises(ValidationError) as exc_long:
            UserCreateSchema(
                username="a" * 151,
                email="a@b.com",
                password="P1",
                password_confirm="P1",
            )
        assert "at most 150 characters" in str(exc_long.value)


class TestBaseUserSchema:
    """Test the BaseUserSchema (Read-only schema)."""

    def test_valid_base_schema(self):
        now = datetime.now()
        data = {
            "id": 1,
            "username": "test",
            "email": "test@test.com",
            "is_active": True,
            "is_stuff": False,
            "is_super_user": False,
            "last_login": None,
            "created_at": now,
            "updated_at": None,
        }
        schema = BaseUserSchema(**data)  # ty:ignore[invalid-argument-type]
        assert schema.id == 1
        assert schema.is_active is True
        assert schema.is_stuff is False
        assert schema.is_super_user is False
        assert schema.created_at == now
