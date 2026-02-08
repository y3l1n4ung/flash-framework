import pytest
from flash_db.expressions import Avg, Count, F, Max, Min, Sum

from .models import Article, Product, Review

pytestmark = pytest.mark.asyncio


class TestAggregation:
    """Tests for annotate() and aggregate() functionality."""

    async def test_basic_annotation(self, db_session):
        """Should add a calculated field to each model instance."""
        await Product.objects.create(db_session, name="P1", price=10, stock=5)
        await Product.objects.create(db_session, name="P2", price=20, stock=10)
        await db_session.commit()

        # Annotate with a simple field-to-field expression
        qs = (
            await Product.objects.annotate(value=F("price") * F("stock"))
            .order_by("name")
            .fetch(db_session)
        )

        assert len(qs) == 2
        assert qs[0].name == "P1"
        assert qs[0].value == 50  # pyright: ignore[reportAttributeAccessIssue]
        assert qs[1].name == "P2"
        assert qs[1].value == 200  # pyright: ignore[reportAttributeAccessIssue]

    async def test_relationship_count_annotation(self, db_session):
        """Should correctly count related objects via annotation."""
        a1 = await Article.objects.create(db_session, title="A1", content="C1")
        a2 = await Article.objects.create(db_session, title="A2", content="C2")

        await Review.objects.create(
            db_session, article_id=a1.id, rating=5, comment="R1"
        )
        await Review.objects.create(
            db_session, article_id=a1.id, rating=4, comment="R2"
        )
        await Review.objects.create(
            db_session, article_id=a2.id, rating=3, comment="R3"
        )
        await db_session.commit()

        qs = (
            await Article.objects.annotate(num_reviews=Count("reviews"))
            .order_by("title")
            .fetch(db_session)
        )

        assert len(qs) == 2
        assert qs[0].title == "A1"
        assert qs[0].num_reviews == 2  # pyright: ignore[reportAttributeAccessIssue]
        assert qs[1].title == "A2"
        assert qs[1].num_reviews == 1  # pyright: ignore[reportAttributeAccessIssue]

    async def test_filter_on_annotated_field(self, db_session):
        """Should allow filtering the QuerySet based on annotated values."""
        # value 10
        await Product.objects.create(db_session, name="Cheap", price=10, stock=1)
        # value 1000
        await Product.objects.create(db_session, name="Expensive", price=100, stock=10)
        await db_session.commit()

        qs = (
            await Product.objects.annotate(total_value=F("price") * F("stock"))
            .filter(total_value__gt=100)
            .fetch(db_session)
        )

        assert len(qs) == 1
        assert qs[0].name == "Expensive"

    async def test_basic_aggregation(self, db_session):
        """Should return summary values for the entire QuerySet."""
        await Product.objects.create(db_session, name="P1", price=10)
        await Product.objects.create(db_session, name="P2", price=30)
        await db_session.commit()

        stats = await Product.objects.aggregate(
            db_session,
            total_price=Sum("price"),
            avg_price=Avg("price"),
            max_price=Max("price"),
            min_price=Min("price"),
            count=Count("id"),
        )

        assert stats["total_price"] == 40
        assert stats["avg_price"] == 20
        assert stats["max_price"] == 30
        assert stats["min_price"] == 10
        assert stats["count"] == 2

    async def test_aggregation_with_filters(self, db_session):
        """Should honor existing QuerySet filters when aggregating."""
        await Product.objects.create(db_session, name="A", price=10)
        await Product.objects.create(db_session, name="B", price=20)
        await Product.objects.create(db_session, name="C", price=30)
        await db_session.commit()

        stats = await Product.objects.filter(price__gte=20).aggregate(
            db_session, total=Sum("price")
        )

        assert stats["total"] == 50  # B(20) + C(30)

    async def test_empty_queryset_aggregation(self, db_session):
        """Should return dictionary with None values when aggregating empty results."""
        stats = await Product.objects.filter(name="nonexistent").aggregate(
            db_session, total=Sum("price"), count=Count("id")
        )

        # SQL Sum on empty set returns None, Count returns 0
        assert stats["total"] is None
        assert stats["count"] == 0

    async def test_multiple_annotations(self, db_session):
        """Should support multiple annotated fields in a single query."""
        p = await Product.objects.create(db_session, name="P", price=10, stock=5)
        await Review.objects.create(db_session, product_id=p.id, rating=5, comment="G")
        await db_session.commit()

        qs = await Product.objects.annotate(
            val=F("price") * 2, num_revs=Count("reviews")
        ).fetch(db_session)

        assert len(qs) == 1
        assert qs[0].val == 20  # pyright: ignore[reportAttributeAccessIssue]
        assert qs[0].num_revs == 1  # pyright: ignore[reportAttributeAccessIssue]

    async def test_annotate_first(self, db_session):
        """Should correctly map annotations when using first()."""
        await Product.objects.create(db_session, name="P", price=10)
        await db_session.commit()

        p = await Product.objects.annotate(doubled=F("price") * 2).first(db_session)
        assert p is not None
        assert p.doubled == 20  # pyright: ignore[reportAttributeAccessIssue]

    async def test_annotate_empty(self):
        """Should return same QuerySet when annotate is called with no args."""
        qs = Product.objects.all()
        assert qs.annotate() is qs

    async def test_annotate_raw_expression(self, db_session):
        """Should support raw SQLAlchemy expressions in annotate()."""
        await Product.objects.create(db_session, name="P1", price=10)
        await db_session.commit()

        from sqlalchemy import func

        qs = await Product.objects.annotate(upper_name=func.upper(Product.name)).fetch(
            db_session
        )

        assert qs[0].upper_name == "P1"  # pyright: ignore[reportAttributeAccessIssue]

    async def test_exclude_on_annotated_field(self, db_session):
        """Should allow excluding records based on annotated values."""
        await Product.objects.create(db_session, name="A", price=10, stock=1)
        await Product.objects.create(db_session, name="B", price=100, stock=10)
        await db_session.commit()

        qs = (
            await Product.objects.annotate(val=F("price") * F("stock"))
            .exclude(val__lt=100)
            .fetch(db_session)
        )

        assert len(qs) == 1
        assert qs[0].name == "B"

    async def test_aggregate_empty_args(self, db_session):
        """Should return empty dict when aggregate is called with no args."""
        res = await Product.objects.aggregate(db_session)
        assert res == {}

    async def test_aggregate_raw_expression(self, db_session):
        """Should support raw SQLAlchemy expressions in aggregate()."""
        await Product.objects.create(db_session, name="P1", price=10)
        await Product.objects.create(db_session, name="P2", price=20)
        await db_session.commit()

        from sqlalchemy import func

        res = await Product.objects.aggregate(db_session, max_p=func.max(Product.price))
        assert res["max_p"] == 20

    async def test_first_with_annotations_no_result(self, db_session):
        """Should return None when first() finds no records even with annotations."""
        p = (
            await Product.objects.annotate(x=F("price"))
            .filter(name="none")
            .first(db_session)
        )
        assert p is None

    async def test_aggregate_with_joins(self, db_session):
        """Should correctly handle joins in aggregate()."""
        a = await Article.objects.create(db_session, title="A1", content="C1")
        await Review.objects.create(db_session, article_id=a.id, rating=5, comment="R1")
        await db_session.commit()

        res = await Article.objects.aggregate(db_session, rev_count=Count("reviews"))
        assert res["rev_count"] == 1

    async def test_complex_filter_with_q_and_annotations(self, db_session):
        """Should support complex Q filters involving both fields and annotations."""
        p1 = await Product.objects.create(db_session, name="P1", price=100, stock=5)
        await Review.objects.create(db_session, product_id=p1.id, rating=5, comment="G")
        await Review.objects.create(db_session, product_id=p1.id, rating=4, comment="G")

        p2 = await Product.objects.create(db_session, name="P2", price=10, stock=1)
        await Review.objects.create(db_session, product_id=p2.id, rating=1, comment="B")
        await db_session.commit()

        from flash_db.expressions import Q

        qs = (
            await Product.objects.annotate(num_revs=Count("reviews"))
            .filter(Q(num_revs__gt=1) | Q(price__lt=20))
            .order_by("name")
            .fetch(db_session)
        )

        assert len(qs) == 2
        assert qs[0].name == "P1"
        assert qs[0].num_revs == 2  # pyright: ignore[reportAttributeAccessIssue]
        assert qs[1].name == "P2"
        assert qs[1].num_revs == 1  # pyright: ignore[reportAttributeAccessIssue]

    async def test_aggregate_annotated_queryset(self, db_session):
        """Should support aggregating values from an annotated QuerySet."""
        await Product.objects.create(db_session, name="P1", price=10, stock=2)
        await Product.objects.create(db_session, name="P2", price=20, stock=3)
        await db_session.commit()

        qs = Product.objects.annotate(total_val=F("price") * F("stock"))

        res = await qs.aggregate(db_session, grand_total=Sum("total_val"))

        assert res["grand_total"] == 80

    async def test_annotate_prevents_redundant_joins(self, db_session):
        """Verify that multiple annotations on the same path only JOIN once."""
        qs = Article.objects.annotate(n1=Count("reviews"), n2=Count("reviews"))
        assert len(qs._joined_relationships) == 1
        await qs.fetch(db_session)

    async def test_annotate_prevents_duplicate_group_by(self, db_session):
        """Verify that repeated annotate calls only add GROUP BY once."""
        qs = Product.objects.annotate(n1=Count("id"))
        initial_count = len(qs._group_by_clauses)

        qs2 = qs.annotate(n2=Count("id"))
        assert len(qs2._group_by_clauses) == initial_count
        await qs2.fetch(db_session)
