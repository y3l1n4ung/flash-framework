from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class BaseUserSchema(BaseModel):
    id: int
    username: str
    email: EmailStr | None
    is_active: bool
    is_stuff: bool
    is_super_user: bool
    last_login: datetime | None
    created_at: datetime
    updated_at: datetime | None


class UserCreateSchema(BaseModel):
    """Payload for registering a new user."""

    username: str = Field(
        ...,
        min_length=3,
        max_length=150,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Username must be alphanumeric, can contain underscores or hyphens.",
    )
    email: EmailStr
    password: str = Field(..., min_length=8, description="Plain text password")
    password_confirm: str = Field(..., min_length=8, description="Confirm password")

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        """Enforce password strength requirements."""
        if not any(char.isdigit() for char in v):
            raise ValueError("Password must contain at least one number")
        if not any(char.isupper() for char in v):
            raise ValueError("Password must contain at least one uppercase letter")
        return v

    @model_validator(mode="after")
    def check_passwords_match(self) -> "UserCreateSchema":
        """Ensure password and password_confirm match."""
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self
