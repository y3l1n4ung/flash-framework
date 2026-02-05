import uuid
from typing import Any, Optional

from flash_db.models import Model, TimestampMixin
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    ForeignKey,
    Numeric,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.type_api import UserDefinedType


class UnsupportedSQLType(UserDefinedType):
    """A type not present in the SQL_TO_PYTHON_TYPE mapping to trigger 'return Any'."""

    def get_col_spec(self, **_kw):
        return "UNSUPPORTED"


# Association table for many-to-many relationship between Article and Tag
article_tag_association = Table(
    "article_tag_association",
    Model.metadata,
    Column("article_id", ForeignKey("articles.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)


class Tag(Model):
    """A tag that can be applied to multiple articles."""

    __tablename__ = "tags"
    name: Mapped[str] = mapped_column(String(50), unique=True)


class Article(Model, TimestampMixin):
    __tablename__ = "articles"

    title: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    comments: Mapped[list["Comment"]] = relationship(
        "Comment",
        back_populates="article",
        cascade="all, delete-orphan",
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag",
        secondary=article_tag_association,
        backref="articles",
    )


class Comment(Model):
    __tablename__ = "comments"
    text: Mapped[str] = mapped_column()
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    article: Mapped["Article"] = relationship("Article", back_populates="comments")


class Job(Model):
    """A model with a UUID primary key."""

    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(  # pyright: ignore[reportIncompatibleVariableOverride]
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(String(100))


class Profile(Model, TimestampMixin):
    __tablename__ = "profiles"
    full_name: Mapped[str] = mapped_column(String(100))
    bio: Mapped[Optional[str]] = mapped_column(
        Text,
        default="No bio provided",
    )  # TODO: check if we should add default to schema or not.
    salary_expectation: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
    api_key_hash: Mapped[str] = mapped_column(String(255))  # Sensitive word 'hash'
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    internal_notes: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    mystery_blob: Mapped[Any] = mapped_column(UnsupportedSQLType, nullable=True)
