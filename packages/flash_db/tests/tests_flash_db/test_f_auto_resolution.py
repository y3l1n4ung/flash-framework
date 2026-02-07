import pytest
from flash_db.expressions import F

from .models import Product

pytestmark = pytest.mark.asyncio


class TestFAutoResolution:
    """Tests for automatic resolution of F expressions in update methods."""

    async def test_queryset_update_auto_resolves_f_expression(self, db_session):
        """Verify that QuerySet.update() automatically resolves F expressions."""
        await Product.objects.create(db_session, name="StockItem", stock=10, price=100)

        # Update using F expression without manual .resolve()
        count = await Product.objects.filter(name="StockItem").update(
            db_session, stock=F("stock") + 5
        )
        assert count == 1

        # Verify update
        item = await Product.objects.get(db_session, Product.name == "StockItem")
        assert item.stock == 15

    async def test_manager_update_auto_resolves_f_expression(self, db_session):
        """Verify that ModelManager.update() automatically resolves F expressions."""
        from decimal import Decimal

        item = await Product.objects.create(
            db_session, name="PriceItem", price=100, stock=0
        )

        # Update using F expression without manual .resolve() via manager
        updated = await Product.objects.update(
            db_session, pk=item.id, price=F("price") * Decimal("1.1")
        )

        assert updated is not None
        assert float(updated.price) == pytest.approx(110.0)

        # Save ID for later use after expiration
        item_id = updated.id

        # Verify persistence
        db_session.expire_all()

        # refreshed handles the fetch via await
        refreshed = await Product.objects.get_by_pk(db_session, item_id)
        assert refreshed is not None
        assert float(refreshed.price) == pytest.approx(110.0)

    async def test_mixed_literal_and_f_expression_update(self, db_session):
        """Verify updates with both literals and F expressions work together."""
        item = await Product.objects.create(
            db_session, name="Mixed", stock=10, price=50
        )

        await Product.objects.filter(id=item.id).update(
            db_session, name="UpdatedMixed", stock=F("stock") - 2
        )

        refreshed = await Product.objects.get_by_pk(db_session, item.id)
        assert refreshed.name == "UpdatedMixed"
        assert refreshed.stock == 8

    async def test_f_expression_field_to_field_assignment(self, db_session):
        """Verify that a field can be updated using another field's value via F."""
        item = await Product.objects.create(
            db_session, name="Field2Field", stock=10, price=5
        )

        # Set price based on stock
        await Product.objects.filter(id=item.id).update(
            db_session, price=F("stock") * 2
        )

        refreshed = await Product.objects.get_by_pk(db_session, item.id)
        assert float(refreshed.price) == 20.0

    async def test_f_expression_chained_arithmetic(self, db_session):
        """Verify complex chained arithmetic in F expressions works."""
        item = await Product.objects.create(
            db_session, name="Chained", stock=10, price=0
        )

        # (10 + 10) * 2 = 40
        await Product.objects.filter(id=item.id).update(
            db_session, stock=(F("stock") + 10) * 2
        )

        refreshed = await Product.objects.get_by_pk(db_session, item.id)
        assert refreshed.stock == 40

    async def test_f_expression_with_column_object(self, db_session):
        """Verify that F expressions can be initialized with model attributes."""
        item = await Product.objects.create(
            db_session, name="ColumnObj", stock=10, price=0
        )

        # Use Product.stock instead of "stock" string
        await Product.objects.filter(id=item.id).update(
            db_session, stock=F(Product.stock) + 1
        )

        refreshed = await Product.objects.get_by_pk(db_session, item.id)
        assert refreshed.stock == 11
