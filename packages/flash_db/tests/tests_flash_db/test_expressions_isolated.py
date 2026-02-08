import pytest
from flash_db.expressions import Avg, Count, F, Max, Min, Q, Sum

from .models import Article, Product


def test_q_object_composition():
    """Test that Q objects combine correctly using bitwise operators."""
    q1 = Q(name="test")
    q2 = Q(price__gt=10)

    # AND
    q_and = q1 & q2
    assert q_and.connector == Q.AND
    assert len(q_and.children) == 2

    # OR
    q_or = q1 | q2
    assert q_or.connector == Q.OR
    assert len(q_or.children) == 2

    # NOT
    q_not = ~q1
    assert q_not.negated is True


def test_q_object_resolution():
    """Test that Q objects resolve to correct SQLAlchemy expressions."""
    # Simple lookup
    q = Q(name="test")
    resolved = q.resolve(Product)
    assert str(resolved) == "products.name = :name_1"

    # Multi-lookup AND
    q_complex = Q(name="test") & Q(price__gt=10)
    resolved_complex = q_complex.resolve(Product)
    assert "products.name = :name_1" in str(resolved_complex)
    assert "products.price > :price_1" in str(resolved_complex)

    # Negation (SQLAlchemy might optimize NOT(==) to !=)
    q_not = ~Q(name="test")
    resolved_not = str(q_not.resolve(Product))
    assert (
        "products.name != :name_1" in resolved_not
        or "NOT (products.name = :name_1)" in resolved_not
    )


def test_all_lookup_operators():
    """Test every supported lookup operator in apply_lookup."""
    from flash_db.expressions import apply_lookup

    col = Product.name
    assert str(apply_lookup(col, "exact", "v")) == "products.name = :name_1"

    iexact_res = apply_lookup(col, "iexact", "v")
    assert str(iexact_res) == "lower(products.name) = lower(:lower_1)"

    contains_res = apply_lookup(col, "contains", "v")
    assert str(contains_res) == "products.name LIKE '%' || :name_1 || '%'"

    icontains_res = apply_lookup(col, "icontains", "v")
    expected = "lower(products.name) LIKE '%' || lower(:lower_1) || '%'"
    assert str(icontains_res) == expected

    assert str(apply_lookup(Product.price, "gt", 5)) == "products.price > :price_1"
    assert str(apply_lookup(Product.price, "gte", 5)) == "products.price >= :price_1"
    assert str(apply_lookup(Product.price, "lt", 5)) == "products.price < :price_1"
    assert str(apply_lookup(Product.price, "lte", 5)) == "products.price <= :price_1"

    # SQLAlchemy uses postcompile for IN
    res_in = str(apply_lookup(Product.price, "in", [1, 2]))
    assert "products.price IN" in res_in

    sw_res = apply_lookup(col, "startswith", "v")
    assert str(sw_res) == "products.name LIKE :name_1 || '%'"

    ew_res = apply_lookup(col, "endswith", "v")
    assert str(ew_res) == "products.name LIKE '%' || :name_1"

    # Use variable to avoid FBT003
    is_null = True
    assert str(apply_lookup(col, "isnull", is_null)) == "products.name IS NULL"

    is_not_null = False
    assert str(apply_lookup(col, "isnull", is_not_null)) == "products.name IS NOT NULL"

    # Unknown lookup should raise ValueError
    with pytest.raises(ValueError, match="Unsupported lookup 'unknown'"):
        apply_lookup(col, "unknown", "v")


def test_parse_lookup():
    """Test parsing of Django-style lookup keys."""
    from flash_db.expressions import parse_lookup

    col, lookup, field_name = parse_lookup(Product, "name")
    assert col == Product.name  # pyright: ignore[reportGeneralTypeIssues]
    assert lookup == "exact"
    assert field_name == "name"

    col, lookup, field_name = parse_lookup(Product, "price__gt")
    assert col == Product.price  # pyright: ignore[reportGeneralTypeIssues]
    assert lookup == "gt"
    assert field_name == "price"


def test_q_object_errors():
    """Test error handling for Q objects."""
    q = Q(name="test")
    with pytest.raises(TypeError, match="Cannot combine Q object with int"):
        _ = q & 1  # type: ignore[operator]


def test_q_object_empty_resolution():
    """Test resolution of empty Q objects."""
    assert Q().resolve(Product) is None


def test_aggregate_base_class():
    """Test base Aggregate class behavior."""
    from flash_db.expressions import Aggregate

    # Use a field that exists on the Product model
    agg = Aggregate("price")
    # Base class has no _func_name
    with pytest.raises(AttributeError):
        agg.resolve(Product)
    assert agg.get_joins(Product) == []


def test_f_expression_all_arithmetic():
    """Test all arithmetic operations for F expressions."""
    f = F("price")
    assert str((f + 1).resolve(Product)) == "products.price + :price_1"
    assert str((f - 1).resolve(Product)) == "products.price - :price_1"
    assert str((f * 2).resolve(Product)) == "products.price * :price_1"
    # SQLAlchemy adds CAST for division, and 2 is parameterized
    res_div = str((f / 2).resolve(Product))
    assert "products.price /" in res_div and "CAST(" in res_div

    # Nested F
    assert str((f + F("stock")).resolve(Product)) == "products.price + products.stock"


def test_q_or_resolution():
    """Test resolution of Q objects with OR connector."""
    q = Q(name="a") | Q(name="b")
    resolved = str(q.resolve(Product))
    assert "products.name = :name_1 OR products.name = :name_2" in resolved


def test_sum_resolution():
    """Test resolution of Sum aggregate."""
    res = str(Sum("price").resolve(Product))
    assert res == "sum(products.price)"


def test_relationship_count_resolution():
    """Test Count resolution for real relationships in models.py."""
    # Article has relationship 'comments'
    count = Count("comments")
    resolved = str(count.resolve(Article))
    assert "count(comments.id)" in resolved

    # Test get_joins
    joins = count.get_joins(Article)
    assert len(joins) == 1
    assert joins[0] is Article.comments


def test_q_resolution_with_annotations():
    """Test that Q objects can resolve using annotations."""
    from sqlalchemy import Column, Integer

    # Mock an annotation (e.g. a count from another query)
    ann_col = Column("annotated_field", Integer)
    annotations = {"annotated_field": ann_col}

    q = Q(annotated_field__gt=5)
    resolved = str(q.resolve(Product, _annotations=annotations))
    assert "annotated_field > :annotated_field_1" in resolved


def test_f_expression_arithmetic_logic():
    """Test that F expressions support arithmetic operations structure."""
    f = F("price")

    f_add = f + 10
    assert len(f_add._ops) == 1
    assert f_add._ops[0] == ("+", 10)

    f_complex = (f * 2) - 5
    assert len(f_complex._ops) == 2
    assert f_complex._ops[0] == ("*", 2)
    assert f_complex._ops[1] == ("-", 5)


def test_aggregate_resolution():
    """Test that aggregates resolve to correct SQLAlchemy functions."""
    # Count
    count = Count("id")
    resolved_count = count.resolve(Product)
    assert str(resolved_count) == "count(products.id)"

    # Sum
    sum_agg = Sum("price")
    resolved_sum = sum_agg.resolve(Product)
    assert str(resolved_sum) == "sum(products.price)"

    # Avg
    avg = Avg("price")
    resolved_avg = avg.resolve(Product)
    assert str(resolved_avg) == "avg(products.price)"

    # Min/Max
    min_agg = Min("price")
    max_agg = Max("price")
    assert str(min_agg.resolve(Product)) == "min(products.price)"
    assert str(max_agg.resolve(Product)) == "max(products.price)"


def test_aggregate_resolve_errors():
    """Test error handling when aggregate field is missing."""
    from flash_db.expressions import Sum

    with pytest.raises(AttributeError, match="not found on model Product"):
        Sum("nonexistent").resolve(Product)

    with pytest.raises(AttributeError, match="not found on model Product"):
        Count("nonexistent").resolve(Product)


def test_f_expression_resolve_errors():
    """Test error handling for F expressions with missing fields."""
    with pytest.raises(AttributeError, match="not found on model Product"):
        F("nonexistent").resolve(Product)


def test_f_expression_resolve_with_annotations():
    """Test that F expressions resolve from annotations."""
    from sqlalchemy import Column, Integer

    ann_col = Column("derived", Integer)
    ann = {"derived": ann_col}
    f = F("derived")
    resolved = f.resolve(Product, _annotations=ann)
    assert resolved is ann_col


def test_aggregate_resolve_from_annotations():
    """Test that aggregates can resolve from existing annotations."""
    from sqlalchemy import func

    # Mock an annotation (e.g. a calculated field)
    ann = {"val_ann": func.lower(Product.name)}

    # Verify each aggregate type correctly identifies and wraps the annotation
    assert (
        str(Count("val_ann").resolve(Product, _annotations=ann))
        == "count(lower(products.name))"
    )
    assert (
        str(Sum("val_ann").resolve(Product, _annotations=ann))
        == "sum(lower(products.name))"
    )
    assert (
        str(Avg("val_ann").resolve(Product, _annotations=ann))
        == "avg(lower(products.name))"
    )
    assert (
        str(Max("val_ann").resolve(Product, _annotations=ann))
        == "max(lower(products.name))"
    )
    assert (
        str(Min("val_ann").resolve(Product, _annotations=ann))
        == "min(lower(products.name))"
    )
