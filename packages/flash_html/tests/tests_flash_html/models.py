from flash_db.models import Model
from sqlalchemy.orm import Mapped, mapped_column


class Product(Model):
    __tablename__ = "test_products"
    name: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(unique=True)
    published: Mapped[bool] = mapped_column(default=True)


class Blog(Model):
    __tablename__ = "test_blogs"
    title: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="draft")
