import pytest
from flash_db import Q

from .models import Article

pytestmark = pytest.mark.asyncio


class TestExpressions:
    async def test_q_objects_or(self, db_session):
        """Test OR combination of Q objects."""
        await Article.objects.create(db_session, title="A")
        await Article.objects.create(db_session, title="B")
        await Article.objects.create(db_session, title="C")

        results = await Article.objects.filter(Q(title="A") | Q(title="B")).fetch(
            db_session
        )
        assert len(results) == 2
        titles = [r.title for r in results]
        assert "A" in titles
        assert "B" in titles

    async def test_q_objects_and(self, db_session):
        """Test AND combination of Q objects."""
        await Article.objects.create(db_session, title="A1", content="X")
        await Article.objects.create(db_session, title="A2", content="Y")

        results = await Article.objects.filter(Q(title="A1") & Q(content="X")).fetch(
            db_session
        )
        assert len(results) == 1
        assert results[0].title == "A1"

    async def test_q_objects_not(self, db_session):
        """Test negation of Q objects."""
        await Article.objects.create(db_session, title="A")
        await Article.objects.create(db_session, title="B")

        results = await Article.objects.filter(~Q(title="A")).fetch(db_session)
        assert all(r.title != "A" for r in results)

    async def test_keyword_filtering(self, db_session):
        """Test simplified filtering using keyword arguments."""
        await Article.objects.create(db_session, title="Keywords", content="Match")

        # filter() with kwargs
        results = await Article.objects.filter(title="Keywords", content="Match").fetch(
            db_session
        )
        assert len(results) == 1
        assert results[0].title == "Keywords"

        # exclude() with kwargs
        results2 = await Article.objects.exclude(title="Keywords").fetch(db_session)
        assert all(r.title != "Keywords" for r in results2)

    async def test_q_object_with_raw_expression(self, db_session):
        """Test Q object combined with a raw SQLAlchemy expression."""
        await Article.objects.create(db_session, title="Mix")

        # Combine Q with direct SQLAlchemy condition
        results = await Article.objects.filter(Q(title="Mix"), Article.id > 0).fetch(
            db_session
        )
        assert len(results) == 1
        assert results[0].title == "Mix"

    async def test_empty_q_returns_none(self):
        """Test that an empty Q object resolves to None."""
        from .models import Article

        q = Q()
        assert q.resolve(Article) is None

    async def test_invalid_q_combination_raises(self):
        """Test that combining Q with non-Q raises TypeError."""
        with pytest.raises(TypeError, match="Cannot combine Q object with"):
            Q(title="A") & "Not a Q"  # type: ignore
