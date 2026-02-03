"""
Models for DetailView + PermissionMixin example application.

Demonstrates model structure for permission testing.
"""

from flash_db.models import Model
from sqlalchemy.orm import Mapped, mapped_column


class Article(Model):
    """Article model with ownership for custom permission examples."""

    __tablename__ = "example_articles"

    title: Mapped[str] = mapped_column()
    slug: Mapped[str] = mapped_column(unique=True)
    content: Mapped[str] = mapped_column()
    author_id: Mapped[int] = mapped_column()  # For ownership permissions
    published: Mapped[bool] = mapped_column(default=True)
