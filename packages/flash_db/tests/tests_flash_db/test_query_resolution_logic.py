import pytest
from flash_db.expressions import F, Q, Resolvable

from .models import Product

pytestmark = pytest.mark.asyncio


class TestQueryResolutionLogic:
    """Specialized tests for query expression resolution and composition."""

    async def test_q_object_resolves_with_annotations(self):
        """Should resolve Q conditions using active query annotations."""
        ann = {"derived": Product.price}
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
