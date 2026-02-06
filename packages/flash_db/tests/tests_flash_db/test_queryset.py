import pytest

from .models import Article

pytestmark = pytest.mark.asyncio


class TestQuerySet:
    """Tests for lazy query building and execution via QuerySet."""

    async def test_filter_criteria_matches_expected_records(self, db_session):
        """Should filter records based on provided column expressions."""
        await Article.objects.create(db_session, title="Match", content="Unique")
        await Article.objects.create(db_session, title="No Match", content="Common")

        results = await Article.objects.filter(Article.content == "Unique").fetch(
            db_session
        )
        assert len(results) == 1
        assert results[0].title == "Match"

    async def test_exclude_criteria_filters_out_records(self, db_session):
        """Should return records that do NOT match the provided criteria."""
        await Article.objects.create(db_session, title="Keep")
        await Article.objects.create(db_session, title="Drop")

        results = await Article.objects.exclude(Article.title == "Drop").fetch(
            db_session
        )
        assert all(r.title == "Keep" for r in results)

    async def test_order_by_sorts_results_correctly(self, db_session):
        """Should return records in the specified sort order."""
        await Article.objects.create(db_session, title="C")
        await Article.objects.create(db_session, title="A")
        await Article.objects.create(db_session, title="B")

        results = await Article.objects.all().order_by(Article.title).fetch(db_session)
        assert [r.title for r in results] == ["A", "B", "C"]

    async def test_only_loads_specific_columns(self, db_session):
        """Should only populate requested fields into the model instance."""
        await Article.objects.create(db_session, title="Only", content="Hidden")

        article = await Article.objects.only("title").first(db_session)
        assert article
        assert article.title == "Only"
        assert "title" in article.__dict__
        assert "content" not in article.__dict__

    async def test_defer_delays_column_loading(self, db_session):
        """Should exclude specific columns from the initial SELECT statement."""
        await Article.objects.create(db_session, title="Defer", content="Lazy")

        article = await Article.objects.defer("content").first(db_session)
        assert article
        assert article.title == "Defer"
        assert "content" not in article.__dict__

    async def test_first_returns_earliest_record_or_none(self, db_session):
        """Should return the first matching record or None for empty sets."""
        await Article.objects.create(db_session, title="First")

        first = await Article.objects.filter(title="First").first(db_session)
        assert first
        assert first.title == "First"

        missing = await Article.objects.filter(title="Missing").first(db_session)
        assert missing is None

    async def test_last_returns_final_record_by_pk_descending(self, db_session):
        """
        Should return the final matching record by reversing sort order
        (default PK desc).
        """
        await Article.objects.create(db_session, title="One")
        await Article.objects.create(db_session, title="Two")

        last = await Article.objects.all().last(db_session)
        assert last
        assert last.title == "Two"

    async def test_values_returns_list_of_dictionaries(self, db_session):
        """Should return raw column data instead of model instances."""
        await Article.objects.create(db_session, title="Dict", content="Data")

        data = await Article.objects.values(db_session, "title")
        assert any(row["title"] == "Dict" for row in data)

    async def test_values_list_returns_tuples_or_flat_list(self, db_session):
        """Should return data as tuples, or a flat list if flat=True."""
        await Article.objects.create(db_session, title="List")

        titles = await Article.objects.values_list(db_session, "title", flat=True)
        assert "List" in titles
