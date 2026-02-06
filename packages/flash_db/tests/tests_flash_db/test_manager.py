from unittest.mock import patch

import pytest

from .models import Article

pytestmark = pytest.mark.asyncio


class TestModelManager:
    """Tests for the ModelManager class and its direct DB operations."""

    async def test_create_and_retrieve_model_instance(self, db_session):
        """Should successfully create a record and fetch it back."""
        article = await Article.objects.create(
            db_session, title="Manager Test", content="Content"
        )
        fetched = await Article.objects.get(db_session, Article.id == article.id)
        assert fetched
        assert fetched.title == "Manager Test"

    async def test_get_raises_error_when_no_match_found(self, db_session):
        """Should raise ValueError when query returns no results."""
        with pytest.raises(ValueError, match="matching query does not exist"):
            await Article.objects.get(db_session, Article.title == "Non-existent")

    async def test_get_raises_error_when_multiple_matches_found(self, db_session):
        """Should raise ValueError when query returns more than one result."""
        await Article.objects.create(db_session, title="Duo", content="Same")
        await Article.objects.create(db_session, title="Duo 2", content="Same")
        with pytest.raises(ValueError, match="returned more than one"):
            await Article.objects.get(db_session, Article.content == "Same")

    async def test_get_by_pk_retrieves_correct_instance(self, db_session):
        """Should fetch a specific record using its primary key."""
        article = await Article.objects.create(db_session, title="PK Test")
        fetched = await Article.objects.get_by_pk(db_session, article.id)
        assert fetched
        assert fetched.id == article.id

    async def test_delete_by_pk_removes_record_successfully(self, db_session):
        """Should delete a record by its primary key and return count 1."""
        article = await Article.objects.create(db_session, title="To Delete")
        count = await Article.objects.delete_by_pk(db_session, article.id)
        assert count == 1
        assert not await Article.objects.filter(id=article.id).exists(db_session)

    async def test_update_modifies_record_and_returns_fresh_instance(self, db_session):
        """Should perform an atomic update and return the fresh data."""
        article = await Article.objects.create(db_session, title="Old")
        updated = await Article.objects.update(db_session, pk=article.id, title="New")
        assert updated
        assert updated.title == "New"

    async def test_update_rolls_back_on_commit_failure(self, db_session):
        """Should trigger session rollback if the database commit fails."""
        article = await Article.objects.create(db_session, title="Rollback Test")

        with (
            patch.object(
                db_session, "rollback", wraps=db_session.rollback
            ) as spied_rollback,
            patch.object(db_session, "commit", side_effect=Exception("Commit failed")),
            pytest.raises(Exception, match="Commit failed"),
        ):
            await Article.objects.update(db_session, pk=article.id, title="Failed New")

        spied_rollback.assert_awaited_once()

    async def test_get_or_create_returns_new_instance_when_missing(self, db_session):
        """Should create record if missing and return (instance, True)."""
        article, created = await Article.objects.get_or_create(
            db_session, title="GOC New", defaults={"content": "New Content"}
        )
        assert created is True
        assert article.title == "GOC New"

    async def test_get_or_create_returns_existing_instance_when_found(self, db_session):
        """Should fetch existing record and return (instance, False)."""
        existing = await Article.objects.create(db_session, title="Existing")
        article, created = await Article.objects.get_or_create(
            db_session, title="Existing"
        )
        assert created is False
        assert article.id == existing.id

    async def test_update_or_create_updates_existing_instance(self, db_session):
        """Should update existing record with defaults and return (instance, False)."""
        await Article.objects.create(db_session, title="UOC", content="Old")
        article, created = await Article.objects.update_or_create(
            db_session, title="UOC", defaults={"content": "New"}
        )
        assert created is False
        assert article.content == "New"

    async def test_exists_and_count_proxy_methods(self, db_session):
        """Should correctly report existence and count via manager shortcuts."""
        await Article.objects.create(db_session, title="Proxy Test")
        assert await Article.objects.exists(db_session, Article.title == "Proxy Test")
        assert (
            await Article.objects.count(db_session, Article.title == "Proxy Test") == 1
        )
