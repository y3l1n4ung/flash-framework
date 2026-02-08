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

    async def test_values_branches_coverage(self, db_session):
        """
        Cover missing branches in values() method:
        no fields, order_by, limit, offset.
        """
        await Article.objects.create(db_session, title="A", content="Data1")
        await Article.objects.create(db_session, title="B", content="Data2")

        # 1. Test values() without fields
        data_all = await Article.objects.all().values(db_session)
        assert len(data_all) >= 2
        assert "title" in data_all[0]
        assert "content" in data_all[0]

        # 2. Test values() with order_by, limit, offset
        data_filtered = (
            await Article.objects.all()
            .order_by(Article.title)
            .limit(1)
            .offset(1)
            .values(db_session, "title")
        )
        assert len(data_filtered) == 1
        assert data_filtered[0]["title"] == "B"

    async def test_values_list_returns_tuples_or_flat_list(self, db_session):
        """Should return data as tuples, or a flat list if flat=True."""
        await Article.objects.create(db_session, title="List")

        titles = await Article.objects.values_list(db_session, "title", flat=True)
        assert "List" in titles

    async def test_queryset_values_with_filter(self, db_session):
        """Should honor filters when calling values()."""
        await Article.objects.create(db_session, title="Match", content="C1")
        await Article.objects.create(db_session, title="Other", content="C2")
        await db_session.commit()

        data = await Article.objects.filter(title="Match").values(db_session, "title")
        assert len(data) == 1
        assert data[0]["title"] == "Match"

    async def test_queryset_values_list_branches(self, db_session):
        """
        Cover branches in values_list(): no fields, ordering, flat=True validation.
        """
        await Article.objects.create(db_session, title="B")
        await Article.objects.create(db_session, title="A")
        await db_session.commit()

        # 1. No fields
        data = await Article.objects.all().values_list(db_session)
        assert len(data) >= 2

        # 2. Ordering
        titles = await Article.objects.order_by("title").values_list(
            db_session, "title", flat=True
        )
        assert list(titles) == ["A", "B"]

        # 3. flat=True validation error
        with pytest.raises(ValueError, match="flat=True can only be used"):
            await Article.objects.values_list(db_session, "title", "content", flat=True)

    async def test_queryset_filter_empty_q(self, db_session):
        """Should handle Q objects that resolve to None."""
        from flash_db.expressions import Q

        qs = Article.objects.filter(Q())
        # Should return everything if Q() is empty
        assert await qs.count(db_session) == 0

    async def test_queryset_filter_invalid_field(self):
        """Should raise ValueError for non-existent fields in keyword lookups."""
        with pytest.raises(ValueError, match="not found on model Article"):
            Article.objects.filter(nonexistent=1)

    async def test_queryset_aggregate_with_existing_having(self, db_session):
        """Should honor existing HAVING clause in aggregate()."""
        from flash_db.expressions import Count

        await Article.objects.create(db_session, title="A")
        await db_session.commit()

        qs = Article.objects.annotate(c=Count("id")).filter(c__gt=0)
        res = await qs.aggregate(db_session, total=Count("id"))
        assert res["total"] == 1

    async def test_queryset_contains_aggregate_direct(self):
        """Should correctly detect aggregates when passed directly to filter."""
        from sqlalchemy import func

        qs = Article.objects.annotate(n=func.count(Article.id)).filter(
            func.count(Article.id) > 0
        )
        assert "HAVING" in str(qs._stmt)

    async def test_queryset_exclude_empty(self):
        """Should return self when exclude is called without args."""
        qs = Article.objects.all()
        assert qs.exclude() is qs

    async def test_queryset_filter_empty(self):
        """Should return self when filter is called without args."""
        qs = Article.objects.all()
        assert qs.filter() is qs

    async def test_queryset_values_list_with_annotation(self, db_session):
        """Should support annotated fields in values_list()."""
        from flash_db.expressions import Count

        await Article.objects.create(db_session, title="A")
        await db_session.commit()

        data = await Article.objects.annotate(c=Count("id")).values_list(
            db_session, "c"
        )
        assert len(data) == 1
        assert data[0][0] == 1

    async def test_queryset_exclude_with_q_aggregate(self, db_session):
        """Should support Q objects with aggregates in exclude()."""
        from flash_db.expressions import Count, Q

        await Article.objects.create(db_session, title="A")
        await db_session.commit()

        qs = Article.objects.annotate(c=Count("id")).exclude(Q(c__gt=1))
        assert "HAVING" in str(qs._stmt)
        results = await qs.fetch(db_session)
        assert len(results) == 1

    async def test_queryset_values_with_having(self, db_session):
        """Should honor HAVING clause when calling values()."""
        from flash_db.expressions import Count

        await Article.objects.create(db_session, title="A")
        await db_session.commit()

        data = (
            await Article.objects.annotate(c=Count("id"))
            .filter(c__gt=0)
            .values(db_session, "c")
        )
        assert len(data) == 1
        assert data[0]["c"] == 1

    async def test_queryset_values_list_with_having(self, db_session):
        """Should honor HAVING clause when calling values_list()."""
        from flash_db.expressions import Count

        await Article.objects.create(db_session, title="A")
        await db_session.commit()

        titles = (
            await Article.objects.annotate(c=Count("id"))
            .filter(c__gt=0)
            .values_list(db_session, "title", flat=True)
        )
        assert list(titles) == ["A"]

    async def test_queryset_exclude_with_aggregate(self, db_session):
        """Should correctly handle aggregates in exclude()."""
        from flash_db.expressions import Count

        await Article.objects.create(db_session, title="A")
        await db_session.commit()

        # Should use HAVING NOT (...)
        qs = Article.objects.annotate(c=Count("id")).exclude(c__gt=1)
        assert "HAVING" in str(qs._stmt)
        results = await qs.fetch(db_session)
        assert len(results) == 1

    async def test_queryset_exclude_with_positional_aggregate(self, db_session):
        """Should handle positional aggregates in exclude()."""
        from sqlalchemy import func

        await Article.objects.create(db_session, title="A")
        await db_session.commit()

        qs = Article.objects.annotate(n=func.count(Article.id)).exclude(
            func.count(Article.id) > 1,
        )
        assert "HAVING" in str(qs._stmt)
        results = await qs.fetch(db_session)
        assert len(results) == 1

    async def test_queryset_exclude_invalid_field(self):
        """Should raise ValueError for non-existent fields."""
        with pytest.raises(ValueError, match="not found on model Article"):
            Article.objects.exclude(nonexistent=1)

    async def test_queryset_contains_aggregate_direct_instance(self):
        """Should return True for direct Aggregate instances."""
        from flash_db.expressions import Count

        qs = Article.objects.all()
        assert qs._contains_aggregate(Count("id")) is True
