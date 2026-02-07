import pytest

from .models import Article, Comment, Tag

pytestmark = pytest.mark.asyncio


class TestRelationships:
    """Tests for relationship loading strategies (JOIN vs SELECT IN)."""

    async def test_select_related_performs_efficient_join(self, db_session):
        """Should load a many-to-one relationship using a single SQL JOIN."""
        article = await Article.objects.create(db_session, title="Parent")
        comment = await Comment.objects.create(
            db_session, text="Child", article_id=article.id
        )
        comment_id = comment.id

        db_session.expire_all()

        # Load comment and its parent article in one query
        fetched = (
            await Comment.objects.filter(id=comment_id)
            .select_related("article")
            .first(db_session)
        )
        assert fetched
        assert fetched.article.title == "Parent"

    async def test_prefetch_related_performs_separate_select_in_queries(
        self, db_session
    ):
        """
        Should load a many-to-many relationship using a secondary SELECT IN query.
        """
        tag1 = await Tag.objects.create(db_session, name="T1")
        tag2 = await Tag.objects.create(db_session, name="T2")
        await Article.objects.create(db_session, title="Prefetch", tags=[tag1, tag2])

        db_session.expire_all()

        # Load article and its tags efficiently
        fetched = (
            await Article.objects.filter(title="Prefetch")
            .prefetch_related("tags")
            .first(db_session)
        )
        assert fetched
        assert len(fetched.tags) == 2
        assert {t.name for t in fetched.tags} == {"T1", "T2"}

    async def test_combined_eager_loading_strategies(self, db_session):
        """
        Should support mixing select_related and prefetch_related in query chain.
        """
        article = await Article.objects.create(db_session, title="Mixed")
        await Comment.objects.create(db_session, text="C", article_id=article.id)

        db_session.expire_all()

        # JOIN for comments, SELECT IN for tags (though empty here)
        fetched = (
            await Article.objects.filter(title="Mixed")
            .select_related("comments")
            .prefetch_related("tags")
            .first(db_session)
        )
        assert fetched
        assert len(fetched.comments) == 1
        assert len(fetched.tags) == 0
