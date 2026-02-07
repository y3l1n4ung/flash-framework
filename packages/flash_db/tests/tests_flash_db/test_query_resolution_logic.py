from typing import TYPE_CHECKING, Any, cast

import pytest
from flash_db.expressions import F, Q, Resolvable

from .models import Product

if TYPE_CHECKING:
    from sqlalchemy.sql import ColumnElement

pytestmark = pytest.mark.asyncio


class TestQueryResolutionLogic:
    """Specialized tests for query expression resolution and composition."""

    async def test_q_object_resolves_with_annotations(self):
        """Should resolve Q conditions using active query annotations."""
        ann: dict[str, "ColumnElement[Any]"] = {
            "derived": cast("ColumnElement[Any]", Product.price)
        }
        q = Q(derived__gt=100)
        resolved = q.resolve(Product, _annotations=ann)
        assert "products.price > " in str(resolved)

    async def test_q_object_fallbacks_to_model_attribute(self):
        """Should fallback to model attributes when annotation is missing."""
        q = Q(name="test")
        resolved = q.resolve(Product)
        assert "products.name = " in str(resolved)

    async def test_q_object_raises_error_on_invalid_field(self):
        """Should raise AttributeError for non-existent field resolution."""
        q = Q(missing="field")
        with pytest.raises(AttributeError):
            q.resolve(Product)

    async def test_q_object_resolves_nested_resolvables(self):
        """Should resolve conditions where the value is another resolvable."""
        q = Q(price=F("stock"))
        resolved = q.resolve(Product)
        assert str(resolved) == "products.price = products.stock"

    async def test_q_object_handles_raw_sqlalchemy_expressions(self):
        """Verify that Q objects correctly adopt raw SQLAlchemy conditions."""
        q = Q(Product.price > 10)
        resolved = q.resolve(Product)
        assert "price > " in str(resolved)

    async def test_f_expression_resolves_field_references(self):
        """Should resolve arithmetic between multiple fields."""
        f = F("price") + F("stock")
        resolved = f.resolve(Product)
        assert str(resolved) == "products.price + products.stock"

        f2 = F("price") - 5
        assert " - " in str(f2.resolve(Product))

    async def test_expression_comply_with_protocol(self):
        """Verify query expressions implement the resolution interface."""

        def check(obj: Resolvable) -> bool:
            return hasattr(obj, "resolve")

        assert check(Q(x="y"))
        assert check(F("z"))

    async def test_queryset_clones_with_statement(self):
        """Verify _clone method adopts a specific statement."""
        qs = Product.objects.all()
        stmt = qs._stmt.limit(5)
        cloned = qs._clone(stmt=stmt)
        assert cloned._stmt is stmt
        assert cloned.model is Product

    async def test_manager_filter_proxies_kwargs(self):
        """Ensure ModelManager correctly passes keyword filters."""
        qs = Product.objects.filter(name="Test")
        assert "products.name = " in str(qs._stmt)

    async def test_queryset_filter_auto_resolves_q_objects(self):
        """Verify that filter() automatically resolves Q objects."""
        qs = Product.objects.filter(Q(name="Auto"))
        assert "products.name = " in str(qs._stmt)
        # Use literal_binds to see the actual value in the string
        compiled = str(qs._stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "'Auto'" in compiled

    async def test_queryset_exclude_auto_resolves_q_objects(self):
        """Verify that exclude() automatically resolves Q objects."""
        qs = Product.objects.exclude(Q(name="Auto"))
        assert "products.name != " in str(qs._stmt)
        compiled = str(qs._stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "'Auto'" in compiled

    async def test_queryset_mixed_filter_expressions(self):
        """Verify that filter() handles mixed raw expressions and Q objects."""
        qs = Product.objects.filter(Product.price > 10, Q(name="Mixed"))
        sql = str(qs._stmt)
        assert "products.price > " in sql
        assert "products.name = " in sql

    async def test_queryset_nested_q_auto_resolution(self):
        """Verify that deeply nested Q objects are resolved correctly."""
        q = Q(Q(name="A") | Q(name="B")) & Q(price__gt=100)
        qs = Product.objects.filter(q)
        sql = str(qs._stmt)
        assert "products.name = " in sql
        assert "OR" in sql
        assert "AND" in sql
        assert "products.price > " in sql

    async def test_queryset_filter_multiple_q_objects(self):
        """Verify that multiple Q objects as positional args are handled."""
        qs = Product.objects.filter(Q(name="A"), Q(price=10))
        sql = str(qs._stmt)
        assert "products.name = " in sql
        assert "products.price = " in sql
        assert "AND" in sql

    async def test_queryset_exclude_multiple_q_objects(self):
        """Verify that multiple Q objects in exclude() are handled."""
        qs = Product.objects.exclude(Q(name="A"), Q(price=10))
        sql = str(qs._stmt)
        assert "products.name != " in sql
        assert "products.price != " in sql

    async def test_queryset_filter_empty_q_object(self):
        """Verify that empty Q objects do not affect the query."""
        qs_baseline = Product.objects.all()
        qs_with_empty = Product.objects.filter(Q())
        assert str(qs_baseline._stmt) == str(qs_with_empty._stmt)

    async def test_queryset_filter_mixed_all_types(self):
        """Verify filter handles SQL expression, Q object, and kwargs together."""

        qs = Product.objects.filter(
            Product.price > 10,  # Raw SQLAlchemy
            Q(name="Mixed"),  # Q object (resolvable)
            stock=5,  # Keyword argument
        )

        sql = str(qs._stmt)

        assert "products.price > " in sql

        assert "products.name = " in sql

        assert "products.stock = " in sql

        assert sql.count("AND") >= 2

    async def test_queryset_filter_q_with_f_expression(self):
        """Verify filter handles Q object containing an F expression."""

        qs = Product.objects.filter(Q(stock__gt=F("price")))

        sql = str(qs._stmt)

        assert "products.stock > products.price" in sql
