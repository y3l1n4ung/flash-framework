from unittest.mock import MagicMock

import pytest
from flash_authentication import AuthenticationResult
from flash_authentication.schemas import AnonymousUser, UserCreateSchema
from pydantic import ValidationError


class TestUserCreateSchema:
    @pytest.mark.parametrize(
        "username, email, password, password_confirm, expected_error",
        [
            # Password Mismatch
            ("user1", "test@a.com", "Pass1234", "Pass5678", "Passwords do not match"),
            # Password Complexity: No Number
            ("user1", "test@a.com", "Password", "Password", "at least one number"),
            # Password Complexity: No Uppercase
            (
                "user1",
                "test@a.com",
                "password123",
                "password123",
                "at least one uppercase",
            ),
            # Username constraints
            ("ab", "test@a.com", "Pass1234", "Pass1234", "at least 3 characters"),
            ("user!", "test@a.com", "Pass1234", "Pass1234", "string_pattern_mismatch"),
        ],
        ids=["mismatch", "no_number", "no_upper", "too_short", "regex_fail"],
    )
    def test_creation_validation_errors(
        self, username, email, password, password_confirm, expected_error
    ):
        """Standardized validation testing using parametrized failure cases."""
        payload = {
            "username": username,
            "email": email,
            "password": password,
            "password_confirm": password_confirm,
        }
        with pytest.raises(ValidationError) as exc:
            UserCreateSchema(**payload)

        assert expected_error in str(exc.value)

    def test_password_mismatch(self):
        payload = {
            "username": "user",
            "email": "test@example.com",
            "password": "Password1",
            "password_confirm": "WrongMatch2",
        }
        with pytest.raises(ValidationError) as exc:
            UserCreateSchema(**payload)

        assert "Passwords do not match" in str(exc.value)

        errors = exc.value.errors()
        assert errors[0]["msg"] == "Value error, Passwords do not match"

    def test_passwords_match(self):
        data = {
            "username": "tester",
            "email": "test@example.com",
            "password": "SecurePassword1",
            "password_confirm": "SecurePassword1",
        }
        schema = UserCreateSchema(**data)

        assert schema.password == schema.password_confirm
        assert isinstance(schema, UserCreateSchema)


class TestAnonymousUser:
    """Tests for the AnonymousUser implementation."""

    def test_default_values(self):
        anon = AnonymousUser()
        assert anon.id is None
        assert not anon.is_authenticated
        assert anon.display_name == "Anonymous"
        assert not anon.email
        assert not anon.is_staff
        assert not anon.is_superuser
        assert str(anon) == "AnonymousUser"
        assert repr(anon) == "<AnonymousUser>"

        assert not anon.is_active
        assert bool(anon) is False


class TestAuthenticationResult:
    """Tests for AuthenticationResult schema."""

    def test_arbitrary_model_type_allowed(self):
        """
        Verify that arbitrary_types_allowed=True is working.
        """
        from flash_db import Model

        mock_db_user = MagicMock(spec=Model)

        result = AuthenticationResult(
            success=True, user=mock_db_user, message="Authenticated via DB"
        )

        assert result.success is True
        assert result.user == mock_db_user

    def test_success_result(self) -> None:
        """Test a successful authentication result container."""
        user = AnonymousUser()
        result = AuthenticationResult(
            success=True, user=user, message="Login successful", extra={"token": "abc"}
        )
        assert result.success is True
        assert result.user == user
        assert result.message == "Login successful"
        assert result.extra["token"] == "abc"
        assert result.errors == []
        assert "success=True" in repr(result)

    def test_failure_result(self) -> None:
        """Test a failed authentication result container."""
        result = AuthenticationResult(
            success=False,
            user=AnonymousUser(),
            message="Invalid credentials",
            errors=["Bad password"],
        )
        assert result.success is False
        assert isinstance(result.user, AnonymousUser)
        assert "Bad password" in result.errors
        assert repr(result) == (
            f"<AuthenticationResult success={result.success} user={result.user}>"
        )
