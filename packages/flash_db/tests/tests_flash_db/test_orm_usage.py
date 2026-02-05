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

    async def test_bulk_create(self, db_session):
        """Test bulk_create functionality."""
        objs = [
            {"title": "Bulk 1", "content": "Content 1"},
            {"title": "Bulk 2", "content": "Content 2"},
            {"title": "Bulk 3", "content": "Content 3"},
        ]
        created = await Article.objects.bulk_create(db_session, objs)
        assert len(created) == 3
        assert created[0].title == "Bulk 1"
        assert created[2].title == "Bulk 3"

        # Verify in DB
        count = await Article.objects.filter(Article.title.startswith("Bulk")).count(
            db_session
        )
        assert count == 3

    async def test_bulk_create_empty(self, db_session):
        """Test bulk_create with empty list."""
        created = await Article.objects.bulk_create(db_session, [])
        assert created == []

    async def test_bulk_create_error(self):
        """Test bulk_create rollback on error."""
        from unittest.mock import AsyncMock

        from sqlalchemy.exc import SQLAlchemyError

        mock_db = AsyncMock()
        mock_db.execute.side_effect = SQLAlchemyError("Mock Bulk Error")

        with pytest.raises(RuntimeError, match="Database error while bulk creating"):
            await Article.objects.bulk_create(mock_db, [{"title": "Fail"}])

        mock_db.rollback.assert_awaited_once()

    async def test_get_by_pk(self, db_session):
        """Test retrieval by primary key."""
        article = await Article.objects.create(db_session, title="PK Test")
        fetched = await Article.objects.get_by_pk(db_session, article.id)
        assert fetched.id == article.id

    async def test_delete_by_pk(self, db_session):
        """Test deletion by primary key."""
        article = await Article.objects.create(db_session, title="Delete PK Test")
        count = await Article.objects.delete_by_pk(db_session, article.id)
        assert count == 1
        assert (
            await Article.objects.filter(Article.id == article.id).exists(db_session)
            is False
        )

    async def test_manager_exists_and_count(self, db_session):
        """Test exists() and count() methods on the manager."""
        await Article.objects.create(db_session, title="MExists 1")

        assert (
            await Article.objects.exists(db_session, Article.title == "MExists 1")
            is True
        )
        assert (
            await Article.objects.exists(db_session, Article.title == "Non-existent")
            is False
        )
        assert (
            await Article.objects.count(db_session, Article.title == "MExists 1") == 1
        )
        assert await Article.objects.count(db_session) >= 1

    async def test_manager_proxy_methods(self, db_session):
        """Test proxy methods on the manager (order_by, limit, offset, values)."""
        await Article.objects.create(db_session, title="A")
        await Article.objects.create(db_session, title="B")
        await Article.objects.create(db_session, title="C")

        # distinct on manager
        dist_results = await Article.objects.distinct().fetch(db_session)
        assert len(dist_results) >= 3

        # order_by on manager
        ord_results = await Article.objects.order_by(Article.title.desc()).fetch(
            db_session
        )
        assert ord_results[0].title == "C"

        # latest on manager
        latest = await Article.objects.latest(db_session, field="title")
        assert latest
        assert latest.title == "C"

        # values_list on manager
        vlist_results = await Article.objects.values_list(
            db_session, "title", flat=True
        )
        assert "A" in vlist_results

        # order_by + limit
        results = (
            await Article.objects.order_by(Article.title.desc())
            .limit(2)
            .fetch(db_session)
        )
        assert len(results) == 2
        assert results[0].title == "C"

        # exclude on manager
        ex_results = await Article.objects.exclude(Article.title == "A").fetch(
            db_session
        )
        assert len(ex_results) >= 2

        # offset on manager
        off_results = (
            await Article.objects.order_by(Article.title).offset(1).fetch(db_session)
        )
        assert off_results[0].title == "B"

        # only on manager
        only_results = await Article.objects.only("title").fetch(db_session)
        assert only_results
        assert only_results[0].title == "A"

        # defer on manager
        defer_results = await Article.objects.defer("content").fetch(db_session)
        assert defer_results
        assert defer_results[0].title == "A"

        # earliest on manager
        earliest = await Article.objects.earliest(db_session, field="title")
        assert earliest
        assert earliest.title == "A"

        # values on manager
        val_results = await Article.objects.order_by(Article.title).values(
            db_session, "title"
        )
        assert val_results[0] == {"title": "A"}

        # Direct values call on manager for coverage
        mgr_vals = await Article.objects.values(db_session, "title")
        assert len(mgr_vals) >= 3

        # Explicitly call limit and offset on manager for coverage
        assert await Article.objects.limit(1).count(db_session) == 1
        assert await Article.objects.offset(1).count(db_session) >= 2


class TestQuerySetUsage:
    async def test_queryset_empty_args(self, db_session):
        """Test methods with empty or default arguments for coverage."""

        await Article.objects.create(db_session, title="Empty Args", content="C")

        # exclude() without conditions
        qs = Article.objects.all()
        assert qs.exclude() is qs

        # values() without fields
        vals = await Article.objects.filter(Article.title == "Empty Args").values(
            db_session
        )
        assert len(vals) == 1
        # Now it should return all fields including title
        assert vals[0]["title"] == "Empty Args"

        # values_list() without fields
        vlist = await Article.objects.filter(Article.title == "Empty Args").values_list(
            db_session
        )
        assert len(vlist) == 1

        # values() with full chain (where, order, limit, offset)
        complex_vals = (
            await Article.objects.order_by(Article.title)
            .limit(1)
            .offset(0)
            .values(db_session, "title")
        )
        assert len(complex_vals) == 1

        # values_list() with full chain
        complex_vlist = (
            await Article.objects.order_by(Article.title)
            .limit(1)
            .offset(0)
            .values_list(db_session, "title")
        )
        assert len(complex_vlist) == 1

    async def test_queryset_empty_filter(self, db_session):
        """Test filter() with no conditions returns the same QuerySet."""
        await Article.objects.create(db_session, title="Empty Filter")
        qs = Article.objects.all()
        assert qs.filter() is qs

    async def test_queryset_bulk_update_no_filter_raises(self, db_session):
        """Test bulk update without filters raises ValueError."""
        with pytest.raises(ValueError, match="Refusing to update without filters"):
            await Article.objects.all().update(db_session, content="New")

    async def test_queryset_bulk_delete_no_filter_raises(self, db_session):
        """Test bulk delete without filters raises ValueError."""
        # Use a fresh queryset from all() to ensure no filters are present
        qs = Article.objects.all()
        with pytest.raises(ValueError, match="Refusing to delete without filters"):
            await qs.delete(db_session)

    async def test_queryset_values_list_invalid_flat(self, db_session):
        """Test values_list(flat=True) with multiple fields raises ValueError."""
        await Article.objects.create(db_session, title="Flat Error")
        with pytest.raises(
            ValueError, match="flat=True can only be used with a single field"
        ) as exc:
            await Article.objects.all().values_list(
                db_session, "id", "title", flat=True
            )
        assert "flat=True" in str(exc.value)

    async def test_complex_chaining(self, db_session):
        """Test chaining of filter, exclude, order_by, only, limit, and fetch."""
        await Article.objects.create(db_session, title="Active 1", content="Keep")
        await Article.objects.create(db_session, title="Active 2", content="Keep")
        await Article.objects.create(db_session, title="Inactive", content="Drop")
        await Article.objects.create(db_session, title="Active Exclude", content="Drop")

        results = await (
            Article.objects.filter(Article.content == "Keep")
            .exclude(Article.title == "Active Exclude")
            .order_by(Article.title.desc())
            .only("title")
            .limit(1)
            .fetch(db_session)
        )

        assert len(results) == 1
        assert results[0].title == "Active 2"
        # Verify that 'content' was NOT loaded into the instance's __dict__.
        assert "title" in results[0].__dict__
        assert "content" not in results[0].__dict__

    async def test_count_and_exists(self, db_session):
        """Test count and exists methods."""
        await Article.objects.create(db_session, title="Count 1")
        await Article.objects.create(db_session, title="Count 2")

        # Test count() on all()
        assert await Article.objects.all().count(db_session) >= 2
        # Test count() on filter()
        assert (
            await Article.objects.filter(Article.title == "Count 1").count(db_session)
            == 1
        )

        assert (
            await Article.objects.filter(Article.title == "Count 1").exists(db_session)
            is True
        )
        assert (
            await Article.objects.filter(Article.title == "Non-existent").exists(
                db_session
            )
            is False
        )

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
            await Article.objects.filter(Article.content == "Same")
            .distinct()
            .fetch(db_session)
        )
        assert len(articles) == 2

    async def test_bulk_update(self, db_session):
        """Test bulk update on a QuerySet."""
        await Article.objects.create(db_session, title="Bulk 1", content="Old")
        await Article.objects.create(db_session, title="Bulk 2", content="Old")

        count = await Article.objects.filter(Article.content == "Old").update(
            db_session, content="New"
        )
        assert count == 2

        updated_count = await Article.objects.filter(Article.content == "New").count(
            db_session
        )
        assert updated_count == 2

    async def test_bulk_delete(self, db_session):
        """Test bulk delete on a QuerySet."""
        await Article.objects.create(db_session, title="Delete 1")
        await Article.objects.create(db_session, title="Delete 2")

        count = await Article.objects.filter(Article.title.startswith("Delete")).delete(
            db_session
        )
        assert count == 2
        assert await Article.objects.all().count(db_session) == 0

    async def test_only_defer(self, db_session):
        """Test only and defer for selective column loading."""
        await Article.objects.create(db_session, title="Only", content="Defer")

        # Only title
        article = (
            await Article.objects.filter(Article.title == "Only")
            .only("title")
            .first(db_session)
        )
        assert article
        assert article.title == "Only"
        # Verify selective loading
        assert "title" in article.__dict__
        assert "content" not in article.__dict__

        # Defer content
        article2 = (
            await Article.objects.filter(Article.title == "Only")
            .defer("content")
            .first(db_session)
        )
        assert article2
        assert article2.title == "Only"
        # Verify selective loading
        assert "title" in article2.__dict__
        assert "content" not in article2.__dict__

    async def test_latest_earliest(self, db_session):
        """Test latest and earliest records."""
        await Article.objects.create(db_session, title="Old")
        await Article.objects.create(db_session, title="New")

        latest = await Article.objects.all().latest(db_session, field="id")
        assert latest
        assert latest.title == "New"

        earliest = await Article.objects.all().earliest(db_session, field="id")
        assert earliest
        assert earliest.title == "Old"

    async def test_values(self, db_session):
        """Test values() method."""
        await Article.objects.create(db_session, title="V1", content="C1")
        await Article.objects.create(db_session, title="V2", content="C2")

        results = (
            await Article.objects.all()
            .order_by(Article.title)
            .values(db_session, "title")
        )
        assert len(results) == 2
        assert results[0] == {"title": "V1"}
        assert results[1] == {"title": "V2"}

    async def test_values_list(self, db_session):
        """Test values_list() method."""
        await Article.objects.create(db_session, title="VL1", content="CL1")

        # Multiple fields
        results = await Article.objects.filter(Article.title == "VL1").values_list(
            db_session, "title", "content"
        )
        assert results == [("VL1", "CL1")]

        # Flat list
        results_flat = await Article.objects.filter(Article.title == "VL1").values_list(
            db_session, "title", flat=True
        )
        assert results_flat == ["VL1"]

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

        assert fetched_article
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
        assert fetched_article
        assert len(fetched_article.tags) == 2
        assert "Tech" in [tag.name for tag in fetched_article.tags]
        assert "Python" in [tag.name for tag in fetched_article.tags]


class TestUUIDPrimaryKey:
    async def test_create_and_get_with_uuid(self, db_session):
        """Test models with UUID primary keys."""
        job = await Job.objects.create(db_session, title="UUID Job")
        fetched_job = await Job.objects.get_by_pk(db_session, job.id)
        assert fetched_job
        assert fetched_job.title == "UUID Job"
