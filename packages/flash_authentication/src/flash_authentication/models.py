from datetime import datetime

from flash_db.models import Model, TimestampMixin
from pydantic import EmailStr
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .hasher import hash_password, verify_password
from .interface import BaseUser


class AuthUserMeta(type(Model), type(BaseUser)):
    pass


class AbstractBaseUser(Model, BaseUser, TimestampMixin, metaclass=AuthUserMeta):
    __abstract__ = True

    username: Mapped[str] = mapped_column(
        String(150), unique=True, index=True, nullable=False
    )
    email: Mapped[EmailStr | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def is_authenticated(self) -> bool:
        raise NotImplementedError

    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def display_name(self) -> str:
        return self.username

    def check_password(self, raw_password: str) -> bool:
        """Verify password against hash using Argon2."""
        return verify_password(hash=self.password_hash, password=raw_password)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = hash_password(raw_password)

    def __str__(self) -> str:
        return self.username

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id}, username='{self.username}')>"


class User(AbstractBaseUser):
    __tablename__ = "flash_authentication_users"


class AnonymousUser(BaseUser):
    """Implementation of BaseUser for unauthenticated visitors."""

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
        """AnonymousUser is falsy."""
        return False
