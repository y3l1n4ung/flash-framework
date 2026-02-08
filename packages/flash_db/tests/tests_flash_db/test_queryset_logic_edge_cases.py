import pytest
from flash_db.expressions import Avg, Count, F, Q, Sum
from flash_db.queryset.base import QuerySetBase
from flash_db.queryset.execution import QuerySetExecution
from flash_db.queryset.resolver import QuerySetResolver
from sqlalchemy import literal_column, select

from .models import Article, Product

pytestmark = pytest.mark.asyncio


async def test_queryset_provides_safe_access_to_statement_criteria():
    """
    Verify that QuerySetBase correctly exposes statement parts via property
    helpers.
    """
    stmt = (
        select(Product)
        .where(Product.price > 10)
        .having(Product.stock > 0)
        .group_by(Product.id)
        .order_by(Product.name)
        .limit(10)
        .offset(5)
    )
    qs = QuerySetBase(Product, stmt)

    assert qs._where_criteria is not None
    assert qs._having_criteria is not None
    assert qs._group_by_clauses is not None
    assert qs._order_by_clauses is not None
    assert qs._limit_clause is not None
    assert qs._offset_clause is not None


async def test_queryset_clone_preserves_internal_state_and_annotations():
    """
    Verify that cloning a QuerySet preserves its model and captures new
    statement state.
    """
    from typing import Any, cast

    stmt1 = select(Product)
    qs1 = QuerySetBase(Product, stmt1, _annotations=cast("Any", {"test": "val"}))

    stmt2 = select(Product).limit(1)
    qs2 = qs1._clone(stmt=stmt2)

    assert qs2._stmt is stmt2
    assert qs2.model is Product
    assert qs2._annotations == {"test": "val"}


async def test_queryset_aggregate_summarizes_entire_result_set_across_all_groups(
    db_session,
):
    """
    Verify that aggregate() returns a global total (16) rather than a single
    group total (5) when used on a QuerySet with annotations and grouping.
    """
    await Product.objects.bulk_create(
        db_session,
        [
            {"name": "Widget A", "price": 10, "stock": 5},
            {"name": "Widget B", "price": 20, "stock": 3},
            {"name": "Gadget C", "price": 30, "stock": 8},
        ],
    )

    result = await (
        Product.objects.annotate(item_count=Count("id"))
        .filter(item_count__gte=1)
        .aggregate(db_session, total_stock=Sum("stock"))
    )
    assert result["total_stock"] == 16


async def test_queryset_aggregate_honors_limit_and_offset_slicing(
    db_session,
):
    """Verify that slicing a query before aggregation only sums the sliced data."""
    await Product.objects.bulk_create(
        db_session,
        [
            {"name": "P1", "price": 10},
            {"name": "P2", "price": 20},
            {"name": "P3", "price": 30},
        ],
    )

    res = (
        await Product.objects.order_by("price")
        .limit(2)
        .aggregate(db_session, total=Sum("price"))
    )
    assert res["total"] == 30  # 10 + 20

    res = (
        await Product.objects.order_by("price")
        .offset(1)
        .aggregate(db_session, total=Sum("price"))
    )
    assert res["total"] == 50  # 20 + 30


async def test_queryset_aggregate_summarizes_multiple_calculated_fields_simultaneously(
    db_session,
):
    """
    Verify that multiple summary fields work correctly when calculated over
    a subquery.
    """
    await Product.objects.bulk_create(
        db_session,
        [
            {"name": "A", "price": 10, "stock": 5},
            {"name": "B", "price": 20, "stock": 15},
        ],
    )

    res = await (
        Product.objects.annotate(val=F("price") * 2)
        .filter(val__gt=10)
        .aggregate(db_session, total_stock=Sum("stock"), avg_price=Avg("price"))
    )
    assert res["total_stock"] == 20
    assert res["avg_price"] == 15.0


async def test_queryset_aggregate_correctly_sums_unique_rows_in_distinct_queries(
    db_session,
):
    """Verify that aggregate() respects distinct() by using a subquery."""
    await Product.objects.bulk_create(
        db_session,
        [
            {"name": "Same", "price": 10},
            {"name": "Same", "price": 10},
        ],
    )

    res = await (
        Product.objects.only("name")
        .distinct()
        .annotate(price_sum=Sum("price"))
        .filter(price_sum__gt=0)
        .aggregate(db_session, total=Sum("price_sum"))
    )
    assert res["total"] == 20


async def test_queryset_aggregate_handles_raw_sqlalchemy_literals_in_subqueries(
    db_session,
):
    """
    Verify that raw SQL literals work in aggregate() even when grouping
    is active.
    """
    await Product.objects.create(db_session, name="P1", price=10)
    await db_session.commit()

    res = await (
        Product.objects.annotate(n=Count("id"))
        .filter(n__gte=1)
        .aggregate(db_session, constant=literal_column("100"))
    )
    assert res["constant"] == 100


async def test_queryset_deduplicates_joins_to_prevent_redundant_sql_clauses(db_session):
    """
    Verify that multiple annotations sharing a relationship path only JOIN
    once.
    """
    qs = Article.objects.annotate(
        num_reviews=Count("reviews"), high_reviews=Count("reviews")
    )
    assert len(qs._joined_relationships) == 1
    await qs.fetch(db_session)


async def test_queryset_recursively_detects_aggregates_in_deeply_nested_expressions():
    """
    Verify deep traversal of expression trees for accurate SQL clause
    routing.
    """
    resolver = QuerySetResolver(Product, select(Product))

    expr = (F("price").resolve(Product) + Count("reviews").resolve(Product)) > 10
    assert resolver._contains_aggregate(expr) is True

    q = Q(name="test") | Q(price__gt=Count("reviews"))
    assert resolver._contains_aggregate(q) is True


async def test_queryset_raises_value_error_on_unfiltered_bulk_update(db_session):
    """Verify that bulk updates without filters raise ValueError."""
    with pytest.raises(ValueError, match="Refusing to update without filters"):
        await Product.objects.all().update(db_session, price=10)


async def test_queryset_raises_value_error_on_unfiltered_bulk_delete(db_session):
    """Verify that bulk deletions without filters raise ValueError."""
    with pytest.raises(ValueError, match="Refusing to delete without filters"):
        await Product.objects.all().delete(db_session)


async def test_f_expression_validates_presence_of_all_arithmetic_operands():
    """
    Verify that F expressions raise ValueError when an operand resolves to
    None.
    """
    f = F("price")
    f._ops.append(("+", None))
    with pytest.raises(ValueError, match=r"Operand resolved to None"):
        f.resolve(Product)


async def test_queryset_values_list_enforces_single_field_for_flat_argument(db_session):
    """
    Verify that values_list raises ValueError when flat=True is used with
    multiple fields.
    """
    qs = Product.objects.all()
    with pytest.raises(
        ValueError, match="flat=True can only be used with a single field"
    ):
        await qs.values_list(db_session, "id", "name", flat=True)


async def test_queryset_first_returns_none_on_empty_result_set(db_session):
    """Verify first() behavior when no database records match the query."""
    qs = Product.objects.filter(name="none")
    res = await qs.first(db_session)
    assert res is None


async def test_queryset_uses_optimized_exists_query(db_session):
    """Verify the efficiency of the optimized EXISTS implementation."""
    await Product.objects.create(db_session, name="P1", price=10)
    await db_session.commit()

    assert await Product.objects.filter(name="P1").exists(db_session) is True
    assert await Product.objects.filter(name="P2").exists(db_session) is False


async def test_queryset_projects_all_columns_by_default_in_projection_stmt():
    """Verify that _build_projection_stmt defaults to full table selection."""
    exec_qs = QuerySetExecution(Product, select(Product))
    stmt = exec_qs._build_projection_stmt()
    assert len(stmt.selected_columns) == len(Product.__table__.columns)
