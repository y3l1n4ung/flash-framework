from typing import Optional
from sqlalchemy import String, ForeignKey
from flash_db.models import Model, TimestampMixin
from sqlalchemy.orm import Mapped, mapped_column, relationship


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
