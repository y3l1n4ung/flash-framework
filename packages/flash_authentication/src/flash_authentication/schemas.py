from datetime import datetime
from typing import Any

from flash_db import Model
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


class AnonymousUser(BaseModel):
    id: None = None
    username: str = ""
    email: None = None
    is_staff: bool = False
    is_superuser: bool = False

    @property
    def is_authenticated(self) -> bool:
        """Anonymous users are never authenticated."""
        return False

    @property
    def is_active(self) -> bool:
        """Anonymous users are not active."""
        return False

    @property
    def display_name(self) -> str:
        """Return display name for anonymous user."""
        return "Anonymous"

    def __str__(self) -> str:
        return "AnonymousUser"

    def __repr__(self) -> str:
        return "<AnonymousUser>"

    def __bool__(self) -> bool:
        """AnonymousUser is falsy in boolean context."""
        return False


class AuthenticationResult(BaseModel):
    """Result from authenticator.

    Attributes:
        success: Whether authentication succeeded.
        user: Authenticated user or AnonymousUser.
        message: Human-readable status message.
        errors: List of error details for debugging/logging.
        extra: Extra data from authenticator (session_id, token, etc).

    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    user: Model | AnonymousUser
    message: str = ""
    errors: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    def __repr__(self) -> str:
        return f"<AuthenticationResult success={self.success} user={self.user}>"


class BaseUserSchema(BaseModel):
    id: int
    username: str
    email: EmailStr | None
    is_active: bool
    is_staff: bool
    is_superuser: bool
    last_login: datetime | None
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class UserCreateSchema(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=150,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description=(
            "Username must be alphanumeric, can contain underscores or hyphens."
        ),
    )
    email: EmailStr
    password: str = Field(..., min_length=8, description="Plain text password")
    password_confirm: str = Field(..., min_length=8, description="Confirm password")

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        """Enforce password strength requirements.

        Args:
            v: Password string.

        Raises:
            ValueError: If password lacks digit or uppercase letter.
        """
        if not any(char.isdigit() for char in v):
            msg = "Password must contain at least one number"
            raise ValueError(msg)
        if not any(char.isupper() for char in v):
            msg = "Password must contain at least one uppercase letter"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def check_passwords_match(self) -> "UserCreateSchema":
        """Ensure password and password_confirm match.

        Raises:
            ValueError: If passwords don't match.
        """
        if self.password != self.password_confirm:
            msg = "Passwords do not match"
            raise ValueError(msg)
        return self
