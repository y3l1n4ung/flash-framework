from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from .models import Product

pytestmark = pytest.mark.asyncio


class TestORMInternalBehavior:
    """Specialized tests for internal ORM mechanics and dialect-specific logic."""

    async def test_bulk_create_falls_back_on_missing_returning_support(
        self, db_session
    ):
        """Should fallback to manual instance creation when RETURNING is missing."""
        mock_bind = MagicMock()
        mock_bind.dialect.name = "mysql"
        mock_bind.dialect.insert_returning = False

        objs = [{"name": "P1", "price": 10}, {"name": "P2", "price": 20}]

        with (
            patch.object(db_session, "get_bind", return_value=mock_bind),
            patch.object(db_session, "execute", return_value=AsyncMock()),
            patch.object(db_session, "commit", new_callable=AsyncMock),
        ):
            results = await Product.objects.bulk_create(db_session, objs)
            assert len(results) == 2
            assert results[0].name == "P1"

    async def test_bulk_create_uses_returning_on_supported_dialects(self, db_session):
        """Should utilize RETURNING on dialects that support it."""
        mock_bind = MagicMock()
        mock_bind.dialect.name = "postgresql"
        mock_bind.dialect.insert_returning = True

        mock_result = MagicMock()
        mock_result.scalars().all.return_value = [Product(name="P1")]

        with (
            patch.object(db_session, "get_bind", return_value=mock_bind),
            patch.object(db_session, "execute", return_value=mock_result),
            patch.object(db_session, "commit", new_callable=AsyncMock),
        ):
            results = await Product.objects.bulk_create(db_session, [{"name": "P1"}])
            assert len(results) == 1

    async def test_bulk_create_handles_ignore_conflicts_branches(self, db_session):
        """Verify ignore_conflicts logic for SQLite and MySQL."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        # SQLite
        mock_bind_sqlite = MagicMock()
        mock_bind_sqlite.dialect.name = "sqlite"
        mock_bind_sqlite.dialect.insert_returning = False

        m_exec = AsyncMock(return_value=mock_result)
        with (
            patch.object(db_session, "get_bind", return_value=mock_bind_sqlite),
            patch.object(db_session, "execute", m_exec),
            patch.object(db_session, "commit", new_callable=AsyncMock),
        ):
            await Product.objects.bulk_create(
                db_session, [{"name": "S"}], ignore_conflicts=True
            )

        # MySQL
        mock_bind_mysql = MagicMock()
        mock_bind_mysql.dialect.name = "mysql"
        mock_bind_mysql.dialect.insert_returning = False
        m_exec_m = AsyncMock(return_value=mock_result)
        with (
            patch.object(db_session, "get_bind", return_value=mock_bind_mysql),
            patch.object(db_session, "execute", m_exec_m),
            patch.object(db_session, "commit", new_callable=AsyncMock),
        ):
            await Product.objects.bulk_create(
                db_session, [{"name": "M"}], ignore_conflicts=True
            )

    async def test_manager_proxies_direct_execution_methods(self, db_session):
        """Verify ModelManager proxy methods correctly build and execute queries."""
        await Product.objects.create(db_session, name="ProxyTest", price=10)

        # 1. Execution methods
        assert await Product.objects.first(db_session) is not None

        last = await Product.objects.last(db_session)
        assert last is not None
        assert last.name == "ProxyTest"

        latest = await Product.objects.latest(db_session, field="id")
        assert latest is not None
        assert latest.name == "ProxyTest"

        earliest = await Product.objects.earliest(db_session, field="id")
        assert earliest is not None
        assert earliest.name == "ProxyTest"

        # 2. Query building methods (proxies to QuerySet)
        # Verify that these methods return a QuerySet with the
        # expected statement modifications
        assert "DISTINCT" in str(Product.objects.distinct()._stmt)
        assert "ORDER BY products.name" in str(Product.objects.order_by("name")._stmt)
        assert "LIMIT :param_1" in str(Product.objects.limit(1)._stmt)
        assert "OFFSET :param_1" in str(Product.objects.offset(0)._stmt)

        # 3. Relationship methods
        assert Product.objects.select_related("id") is not None
        assert Product.objects.prefetch_related("id") is not None

    async def test_manager_get_or_create_creation_path(self, db_session):
        """Verify get_or_create creation branch."""
        obj, created = await Product.objects.get_or_create(
            db_session, name="NewGC", price=100
        )
        assert created is True
        assert obj.name == "NewGC"

    async def test_manager_update_or_create_creation_path(self, db_session):
        """Verify update_or_create creation branch."""
        obj, created = await Product.objects.update_or_create(
            db_session, defaults={"price": 200}, name="NewUC"
        )
        assert created is True
        assert obj.price == 200

    async def test_queryset_exclude_with_kwargs(self, db_session):
        """Verify exclude() with keyword arguments hits expected branch."""
        await Product.objects.create(db_session, name="ExcludeMe", price=10)
        qs = Product.objects.exclude(name="ExcludeMe")
        results = await qs.fetch(db_session)
        for r in results:
            assert r.name != "ExcludeMe"

    async def test_queryset_values_with_filter(self, db_session):
        """Verify values() correctly applies existing where criteria."""
        await Product.objects.create(db_session, name="ValueFilter", price=100)
        data = await Product.objects.filter(price=100).values(db_session, "name")
        assert len(data) == 1
        assert data[0]["name"] == "ValueFilter"

    async def test_queryset_methods_return_self_when_no_args_provided(self):
        """Should return original QuerySet instance if no arguments are passed."""
        qs = Product.objects.all()
        assert qs.filter() is qs
        assert qs.exclude() is qs

    async def test_values_list_flat_error_on_multiple_fields(self, db_session):
        """Should raise ValueError when flat=True is used with multiple fields."""
        with pytest.raises(ValueError, match="only be used with a single field"):
            await Product.objects.values_list(db_session, "name", "price", flat=True)

    async def test_queryset_values_list_branches(self, db_session):
        """Verify values_list branches."""
        await Product.objects.create(db_session, name="VList", price=5)
        res = (
            await Product.objects.filter(price=5)
            .order_by("name")
            .limit(1)
            .offset(0)
            .values_list(db_session)
        )
        assert len(res) == 1

    async def test_bulk_update_raises_on_missing_id(self, db_session):
        """Should raise ValueError if any object in bulk_update is missing an id."""
        objs = [Product(name="NoID")]  # No id set
        with pytest.raises(ValueError, match="All objects must have an id"):
            await Product.objects.bulk_update(db_session, objs, ["name"])
