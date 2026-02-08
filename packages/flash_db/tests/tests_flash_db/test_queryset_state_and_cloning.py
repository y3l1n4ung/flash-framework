from flash_db.queryset.base import QuerySetBase
from sqlalchemy import select

from .models import Product


def test_queryset_provides_safe_access_to_statement_criteria():
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


def test_queryset_clone_preserves_internal_state_and_annotations():
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
