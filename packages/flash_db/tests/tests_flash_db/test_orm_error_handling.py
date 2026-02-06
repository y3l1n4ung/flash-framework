from unittest.mock import patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from .models import Product

pytestmark = pytest.mark.asyncio


class TestORMErrorHandling:
    """Specialized tests for ORM error states and rollbacks."""

    async def test_queryset_refuses_unfiltered_update(self, db_session):
        """Should raise ValueError when update is attempted without filters."""
        with pytest.raises(ValueError, match="Refusing to update without filters"):
            await Product.objects.all().update(db_session, name="New")

    async def test_queryset_refuses_unfiltered_delete(self, db_session):
        """Should raise ValueError when delete is attempted without filters."""
        with pytest.raises(ValueError, match="Refusing to delete without filters"):
            await Product.objects.all().delete(db_session)

    async def test_manager_update_raises_error_for_missing_pk(self, db_session):
        """Should raise descriptive ValueError when update targets a missing PK."""
        with pytest.raises(ValueError, match="Product with id 99999 not found"):
            await Product.objects.update(db_session, 99999, name="New")

    async def test_manager_delete_raises_error_on_missing_pk_if_requested(
        self, db_session
    ):
        """Should raise descriptive ValueError on missing PK delete if requested."""
        with pytest.raises(ValueError, match="Product with id 99999 not found"):
            await Product.objects.delete_by_pk(db_session, 99999, raise_if_missing=True)

    async def test_manager_delete_rolls_back_on_sqlalchemy_failure(self, db_session):
        """Should ensure consistency by rolling back on SQL failure during delete."""
        p = await Product.objects.create(db_session, name="ToDel", price=1)
        pid = p.id
        with (
            patch.object(db_session, "execute", side_effect=SQLAlchemyError("Fail")),
            pytest.raises(RuntimeError, match="Database error while deleting"),
        ):
            await Product.objects.delete_by_pk(db_session, pid)

    async def test_manager_delete_rolls_back_on_generic_exception(self, db_session):
        """Should propagate generic exceptions while ensuring session rollback."""
        p = await Product.objects.create(db_session, name="GenericFail", price=1)
        pid = p.id
        with (
            patch.object(db_session, "execute", side_effect=Exception("Panic")),
            pytest.raises(Exception, match="Panic"),
        ):
            await Product.objects.delete_by_pk(db_session, pid)

    async def test_manager_update_rolls_back_on_sqlalchemy_failure(self, db_session):
        """Should ensure consistency by rolling back on SQL failure during update."""
        p = await Product.objects.create(db_session, name="ToUpd", price=1)
        pid = p.id
        with (
            patch.object(db_session, "execute", side_effect=SQLAlchemyError("Fail")),
            pytest.raises(RuntimeError, match="Database error while updating"),
        ):
            await Product.objects.update(db_session, pid, name="New")

    async def test_manager_update_rolls_back_on_generic_exception(self, db_session):
        """Should ensure rollback on generic exceptions during update."""
        p = await Product.objects.create(db_session, name="GenericUpd", price=1)
        pid = p.id
        with (
            patch.object(db_session, "execute", side_effect=Exception("Boom")),
            pytest.raises(Exception, match="Boom"),
        ):
            await Product.objects.update(db_session, pid, name="New")

    async def test_bulk_create_wraps_sqlalchemy_failure(self, db_session):
        """Should wrap SQLAlchemyError in RuntimeError during batch creation."""
        with (
            patch.object(db_session, "execute", side_effect=SQLAlchemyError("Fail")),
            pytest.raises(RuntimeError, match="Database error while bulk creating"),
        ):
            await Product.objects.bulk_create(db_session, [{"name": "X"}])

    async def test_bulk_update_wraps_sqlalchemy_failure(self, db_session):
        """Should wrap SQLAlchemyError in RuntimeError during batch updates."""
        p = await Product.objects.create(db_session, name="P", price=1)
        with (
            patch.object(db_session, "execute", side_effect=SQLAlchemyError("Fail")),
            pytest.raises(RuntimeError, match="Database error while bulk updating"),
        ):
            await Product.objects.bulk_update(db_session, [p], ["name"])

    async def test_manager_get_raises_on_empty_results(self, db_session):
        """Should raise ValueError when get() finds no records."""
        with pytest.raises(ValueError, match="matching query does not exist"):
            await Product.objects.get(db_session, Product.id == 999)

    async def test_manager_get_raises_on_multiple_results(self, db_session):
        """Should raise ValueError when get() finds multiple records."""
        await Product.objects.create(db_session, name="Dup", price=1)
        await Product.objects.create(db_session, name="Dup", price=2)
        with pytest.raises(ValueError, match="returned more than one"):
            await Product.objects.get(db_session, Product.name == "Dup")

    async def test_get_by_pk_raises_error_for_missing_record(self, db_session):
        """Should raise descriptive ValueError on missing record get_by_pk."""
        with pytest.raises(ValueError, match="matching query does not exist"):
            await Product.objects.get_by_pk(db_session, 999)
