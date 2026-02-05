from unittest.mock import patch

import pytest
from sqlalchemy import or_

from .models import Article, Comment, Job, Tag

pytestmark = pytest.mark.asyncio


class TestModelManagerUsage:
    async def test_create_and_get(self, db_session):
        """Test creating a model instance and then retrieving it."""
        article = await Article.objects.create(
            db_session, title="Test Get", content="Content"
        )
        fetched = await Article.objects.get(db_session, Article.id == article.id)
        assert fetched.title == "Test Get"

    async def test_get_no_match(self, db_session):
        """Test that get() raises an error if no object is found."""
        with pytest.raises(ValueError):
            await Article.objects.get(db_session, Article.title == "Non-existent")

    async def test_get_multiple_matches(self, db_session):
        """Test that get() raises an error if multiple objects are found."""
        await Article.objects.create(db_session, title="Article 1", content="Same")
        await Article.objects.create(db_session, title="Article 2", content="Same")
        with pytest.raises(ValueError):
            await Article.objects.get(db_session, Article.content == "Same")

    async def test_all(self, db_session):
        """Test that all() retrieves all objects."""
        await Article.objects.create(db_session, title="All 1")
        await Article.objects.create(db_session, title="All 2")
        articles = await Article.objects.all().fetch(db_session)
        assert len(articles) >= 2

    async def test_filter(self, db_session):
        """Test filtering objects."""
        await Article.objects.create(db_session, title="Filter Test", content="Unique")
        articles = await Article.objects.filter(Article.content == "Unique").fetch(
            db_session
        )
        assert len(articles) == 1
        assert articles[0].title == "Filter Test"

    async def test_update_generic_exception_rollback(self, db_session):
        """Test that a generic exception during update triggers a rollback."""
        article = await Article.objects.create(
            db_session, title="Generic Exception Test"
        )

        # Spy on the real rollback method and patch the commit method simultaneously
        with (
            patch.object(
                db_session, "rollback", wraps=db_session.rollback
            ) as spied_rollback,
            patch.object(db_session, "commit", side_effect=Exception("Commit failed")),
            pytest.raises(Exception, match="Commit failed"),
        ):
            await Article.objects.update(db_session, pk=article.id, title="New Title")

        # The generic exception should have triggered a rollback
        spied_rollback.assert_awaited_once()

    async def test_get_or_create(self, db_session):
        """Test get_or_create functionality."""
        # Create new
        article, created = await Article.objects.get_or_create(
            db_session, title="GOC New", defaults={"content": "New Content"}
        )
        assert created is True
        assert article.title == "GOC New"

        # Get existing
        article2, created = await Article.objects.get_or_create(
            db_session, title="GOC New"
        )
        assert created is False
        assert article2.id == article.id

    async def test_update_or_create(self, db_session):
        """Test update_or_create functionality."""
        # Create new
        article, created = await Article.objects.update_or_create(
            db_session, title="UOC New", defaults={"content": "Initial"}
        )
        assert created is True
        assert article.content == "Initial"

        # Update existing
        article2, created = await Article.objects.update_or_create(
            db_session, title="UOC New", defaults={"content": "Updated"}
        )
        assert created is False
        assert article2.id == article.id
        assert article2.content == "Updated"


class TestQuerySetUsage:
    async def test_chaining_filters(self, db_session):
        """Test chaining multiple filter() calls."""
        await Article.objects.create(
            db_session, title="Chaining", content="Chain Content"
        )
        articles = (
            await Article.objects.filter(Article.title == "Chaining")
            .filter(Article.content == "Chain Content")
            .fetch(db_session)
        )
        assert len(articles) == 1

    async def test_exclude(self, db_session):
        """Test excluding records."""
        await Article.objects.create(db_session, title="A")
        await Article.objects.create(db_session, title="B")
        articles = await Article.objects.exclude(Article.title == "A").fetch(db_session)
        assert len(articles) == 1
        assert articles[0].title == "B"

    async def test_distinct(self, db_session):
        """Test distinct results."""
        await Article.objects.create(db_session, title="A", content="Same")
        await Article.objects.create(db_session, title="B", content="Same")
        articles = (
            await Article.objects.filter(Article.content == "Same").distinct().fetch(db_session)
        )
        assert len(articles) == 2

    async def test_only_defer(self, db_session):
        """Test only and defer for selective column loading."""
        await Article.objects.create(db_session, title="Only", content="Defer")

        # Only title
        article = (
            await Article.objects.filter(Article.title == "Only")
            .only("title")
            .first(db_session)
        )
        assert article is not None
        assert article.title == "Only"

        # Defer content
        article2 = (
            await Article.objects.filter(Article.title == "Only")
            .defer("content")
            .first(db_session)
        )
        assert article2 is not None
        assert article2.title == "Only"

    async def test_latest_earliest(self, db_session):
        """Test latest and earliest records."""
        await Article.objects.create(db_session, title="Old")
        await Article.objects.create(db_session, title="New")

        latest = await Article.objects.all().latest(db_session, field="id")
        assert latest is not None
        assert latest.title == "New"

        earliest = await Article.objects.all().earliest(db_session, field="id")
        assert earliest is not None
        assert earliest.title == "Old"

    async def test_or_queries(self, db_session):
        """Test OR queries using SQLAlchemy's or_()."""
        await Article.objects.create(db_session, title="OR Test 1")
        await Article.objects.create(db_session, title="OR Test 2")
        articles = await Article.objects.filter(
            or_(Article.title == "OR Test 1", Article.title == "OR Test 2")
        ).fetch(db_session)
        assert len(articles) == 2

    async def test_order_by(self, db_session):
        """Test ordering of results."""
        await Article.objects.create(db_session, title="C")
        await Article.objects.create(db_session, title="A")
        await Article.objects.create(db_session, title="B")
        articles = await Article.objects.all().order_by(Article.title).fetch(db_session)
        assert articles[0].title == "A"
        assert articles[1].title == "B"
        assert articles[2].title == "C"

    async def test_limit_and_offset(self, db_session):
        """Test limit() and offset() for pagination."""
        for i in range(5):
            await Article.objects.create(db_session, title=f"Paginate {i}")

        articles = (
            await Article.objects.all()
            .order_by(Article.title)
            .limit(2)
            .offset(1)
            .fetch(db_session)
        )
        assert len(articles) == 2
        # Assuming titles are 'Paginate 0', 'Paginate 1', ...
        assert "Paginate 1" in articles[0].title
        assert "Paginate 2" in articles[1].title


class TestRelationships:
    async def test_one_to_many(self, db_session):
        """Test one-to-many relationship."""
        article = await Article.objects.create(db_session, title="One-to-Many")
        await Comment.objects.create(
            db_session, text="Comment 1", article_id=article.id
        )
        await Comment.objects.create(
            db_session, text="Comment 2", article_id=article.id
        )

        # Eagerly load the 'comments' relationship
        fetched_article = (
            await Article.objects.filter(Article.title == "One-to-Many")
            .load_related("comments")
            .first(db_session)
        )

        assert fetched_article is not None
        assert len(fetched_article.comments) == 2

    async def test_many_to_many(self, db_session):
        """Test many-to-many relationship."""
        tag1 = await Tag.objects.create(db_session, name="Tech")
        tag2 = await Tag.objects.create(db_session, name="Python")
        await Article.objects.create(
            db_session, title="Many-to-Many", tags=[tag1, tag2]
        )

        # Re-fetch the article to verify the relationship was saved
        fetched_article = (
            await Article.objects.filter(Article.title == "Many-to-Many")
            .load_related("tags")
            .first(db_session)
        )
        assert fetched_article is not None
        assert len(fetched_article.tags) == 2
        assert "Tech" in [tag.name for tag in fetched_article.tags]
        assert "Python" in [tag.name for tag in fetched_article.tags]


class TestUUIDPrimaryKey:
    async def test_create_and_get_with_uuid(self, db_session):
        """Test models with UUID primary keys."""
        job = await Job.objects.create(db_session, title="UUID Job")
        fetched_job = await Job.objects.get_by_pk(db_session, job.id)
        assert fetched_job is not None
        assert fetched_job.title == "UUID Job"
