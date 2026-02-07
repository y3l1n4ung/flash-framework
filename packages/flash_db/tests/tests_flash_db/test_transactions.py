import pytest
from flash_db import atomic
from sqlalchemy.exc import IntegrityError

from .models import Article

pytestmark = pytest.mark.asyncio


class TestTransactions:
    """Tests for transaction management and the atomic utility."""

    async def test_atomic_context_manager_commit(self, db_session):
        """Should automatically commit changes on successful block exit."""
        async with atomic(db_session):
            await Article.objects.create(db_session, title="Atomic CM Success")

        # Verify persistence after block
        fetched = await Article.objects.get(
            db_session, Article.title == "Atomic CM Success"
        )
        assert fetched

    async def test_atomic_context_manager_rollback(self, db_session):
        """Should automatically rollback changes if an exception occurs."""
        msg = "Intentional Error"
        with pytest.raises(RuntimeError, match=msg):
            async with atomic(db_session):
                await Article.objects.create(db_session, title="Should Rollback")
                raise RuntimeError(msg)

        # Verify it does NOT exist
        exists = await Article.objects.filter(
            Article.title == "Should Rollback"
        ).exists(db_session)
        assert not exists

    async def test_atomic_decorator_commit(self, db_session):
        """Should automatically commit when used as a decorator."""

        @atomic(db_session)
        async def create_article():
            await Article.objects.create(db_session, title="Atomic Decorator Success")

        await create_article()

        fetched = await Article.objects.get(
            db_session, Article.title == "Atomic Decorator Success"
        )
        assert fetched

    async def test_atomic_decorator_rollback(self, db_session):
        """Should automatically rollback when a decorated function fails."""
        msg = "Decorator Fail"

        @atomic(db_session)
        async def fail_task():
            await Article.objects.create(db_session, title="Decorator Rollback")
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match=msg):
            await fail_task()

        exists = await Article.objects.filter(
            Article.title == "Decorator Rollback"
        ).exists(db_session)
        assert not exists

    async def test_nested_atomic_savepoints(self, db_session):
        """Should support nested atomic blocks using SAVEPOINTs."""

        async def fail_inner():
            await Article.objects.create(db_session, title="Inner")
            msg = "Inner Fail"
            raise RuntimeError(msg)

        async with atomic(db_session):
            await Article.objects.create(db_session, title="Outer")

            try:
                async with atomic(db_session):
                    await fail_inner()
            except RuntimeError:
                pass

            await Article.objects.create(db_session, title="Outer Continued")

        # Outer and Outer Continued should exist, Inner should be rolled back
        assert await Article.objects.filter(Article.title == "Outer").exists(db_session)
        assert await Article.objects.filter(Article.title == "Outer Continued").exists(
            db_session
        )
        assert not await Article.objects.filter(Article.title == "Inner").exists(
            db_session
        )

    async def test_create_integrity_error_within_atomic(self, db_session):
        """Verify IntegrityError triggers rollback within atomic block."""
        # title is non-nullable. Passing None triggers an IntegrityError.
        with pytest.raises(IntegrityError):
            async with atomic(db_session):
                await Article.objects.create(db_session, title=None)

        # Check session is still usable but transaction was rolled back
        await Article.objects.create(db_session, title="Post-Error Success")
        await db_session.commit()
        exists = await Article.objects.filter(title="Post-Error Success").exists(
            db_session
        )
        assert exists
