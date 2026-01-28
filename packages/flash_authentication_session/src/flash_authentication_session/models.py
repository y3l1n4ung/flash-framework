import secrets
from datetime import datetime, timezone

from flash_authentication.models import USER_TABLE_NAME
from flash_db.models import Model
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column


class UserSession(Model):
    __tablename__ = "flash_authentication_sessions"
    session_key: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        default=lambda: secrets.token_urlsafe(32),
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey(f"{USER_TABLE_NAME}.id", ondelete="CASCADE"),
        index=True,
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    @property
    def is_expired(self) -> bool:
        """Check if the session has passed its expiry time."""
        if self.expires_at.tzinfo:
            return datetime.now(self.expires_at.tzinfo) > self.expires_at
        return datetime.now(timezone.utc) > self.expires_at
