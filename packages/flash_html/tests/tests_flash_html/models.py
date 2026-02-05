from flash_db.models import Model
from sqlalchemy.orm import Mapped, mapped_column


class HTMLTestProduct(Model):
    __tablename__ = "html_test_products"
    name: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(unique=True)
    published: Mapped[bool] = mapped_column(default=True)


class HTMLTestBlog(Model):
    __tablename__ = "html_test_blogs"
    title: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default="draft")


class HTMLTestArticle(Model):
    __tablename__ = "html_test_articles"
    title: Mapped[str] = mapped_column(unique=True)
    slug: Mapped[str] = mapped_column(unique=True)
    content: Mapped[str]
    author_id: Mapped[int] = mapped_column()
    published: Mapped[bool] = mapped_column(default=True)
