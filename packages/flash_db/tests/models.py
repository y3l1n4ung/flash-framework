from sqlalchemy.sql.type_api import UserDefinedType
from typing import Optional, Any
from sqlalchemy import String, ForeignKey, Numeric, Text, Boolean, JSON
from flash_db.models import Model, TimestampMixin
from sqlalchemy.orm import Mapped, mapped_column, relationship


class UnsupportedSQLType(UserDefinedType):
    """A type not present in the SQL_TO_PYTHON_TYPE mapping to trigger 'return Any'."""

    def get_col_spec(self, **kw):
        return "UNSUPPORTED"


class Article(Model, TimestampMixin):
    __tablename__ = "articles"

    title: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    comments: Mapped[list["Comment"]] = relationship(
        "Comment", back_populates="article"
    )


class Comment(Model):
    __tablename__ = "comments"
    text: Mapped[str] = mapped_column()
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"))
    article: Mapped["Article"] = relationship("Article", back_populates="comments")


class Profile(Model, TimestampMixin):
    __tablename__ = "profiles"
    full_name: Mapped[str] = mapped_column(String(100))
    bio: Mapped[Optional[str]] = mapped_column(
        Text, default="No bio provided"
    )  # TODO: check if we should add default to schema or not.
    salary_expectation: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
    api_key_hash: Mapped[str] = mapped_column(String(255))  # Sensitive word 'hash'
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    internal_notes: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    mystery_blob: Mapped[Any] = mapped_column(UnsupportedSQLType, nullable=True)
