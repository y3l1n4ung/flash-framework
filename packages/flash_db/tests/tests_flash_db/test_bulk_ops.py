import pytest
from sqlalchemy.exc import IntegrityError

from .models import Article

pytestmark = pytest.mark.asyncio


class TestBulkOperations:
    """Tests for efficient batch database operations."""

    async def test_bulk_create_returns_empty_list_for_empty_input(self, db_session):
        """Should return empty list without error when no objects are provided."""
        results = await Article.objects.bulk_create(db_session, [])
        assert results == []

    async def test_bulk_create_skips_duplicates_when_ignore_conflicts_is_true(
        self, db_session
    ):
        """
        Should skip conflicting records when ignore_conflicts=True.
        """
        await Article.objects.create(db_session, title="Duplicate")

        objs = [
            {"title": "Duplicate", "content": "Will be ignored"},
            {"title": "Unique", "content": "Will be created"},
        ]

        await Article.objects.bulk_create(db_session, objs, ignore_conflicts=True)

        titles = await Article.objects.values_list(db_session, "title", flat=True)
        assert "Unique" in titles
        assert "Duplicate" in titles
        assert len(titles) == 2

    async def test_bulk_create_raises_error_on_conflict_without_ignore(
        self, db_session
    ):
        """
        Should raise IntegrityError on conflict when ignore_conflicts=False.
        """
        await Article.objects.create(db_session, title="Conflict")

        objs = [{"title": "Conflict"}]
        with pytest.raises(IntegrityError):
            await Article.objects.bulk_create(db_session, objs, ignore_conflicts=False)

    async def test_bulk_update_successfully_updates_multiple_fields_across_records(
        self, db_session
    ):
        """Should update multiple columns for multiple records in a single statement."""
        a1 = await Article.objects.create(db_session, title="A1", content="Old")
        a2 = await Article.objects.create(db_session, title="A2", content="Old")

        a1.title = "New A1"
        a1.content = "New C1"
        a2.title = "New A2"
        a2.content = "New C2"

        count = await Article.objects.bulk_update(
            db_session, [a1, a2], fields=["title", "content"]
        )
        assert count == 2

        db_session.expire_all()
        results = await Article.objects.order_by("id").fetch(db_session)
        assert results[0].title == "New A1"
        assert results[1].content == "New C2"

    async def test_bulk_update_returns_zero_for_empty_input(self, db_session):
        """Should return 0 without executing a query when input is empty."""
        assert await Article.objects.bulk_update(db_session, [], ["title"]) == 0
        assert await Article.objects.bulk_update(db_session, [Article(id=1)], []) == 0

    async def test_bulk_update_returns_zero_when_no_records_match_ids(self, db_session):
        """
        Should return 0 (rowcount) if the provided IDs do not exist in the database.
        """
        a = Article(id=99999, title="Ghost")
        count = await Article.objects.bulk_update(db_session, [a], ["title"])
        assert count == 0
