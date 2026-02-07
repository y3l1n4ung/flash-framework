from typing import Sequence
from unittest.mock import AsyncMock, patch

import pytest
from flash_db import db
from sqlalchemy.exc import IntegrityError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Article, Comment

pytestmark = pytest.mark.asyncio


async def create_article(db_session, **kwargs):
    """Helper to create articles for testing."""
    return await Article.objects.create(
        db_session,
        title=kwargs.get("title", "Default Title"),
        content=kwargs.get("content", "Default Content"),
    )


async def test_require_session_factory_raises_runtime_error():
    """Tests factory is None check."""
    with (
        patch("flash_db.db._session_factory", None),
        pytest.raises(RuntimeError, match=r"Database not initialized"),
    ):
        db._require_session_factory()


async def test_init_db_sqlite_executes_fk_path():
    """
    Covers SQLite-specific branch including FK pool listener.
    """
    db.init_db("sqlite+aiosqlite:///:memory:")

    # session factory must be created
    assert db._session_factory


async def test_get_db_yields_session():
    """
    Ensure get_db yields a usable AsyncSession.
    """
    db.init_db("sqlite+aiosqlite:///:memory:")

    async for session in db.get_db():
        assert isinstance(session, AsyncSession)


async def test_get_db_raises_runtime_error_uninitialized():
    """Tests the generator safety without markers."""
    with (
        patch("flash_db.db._session_factory", None),
        pytest.raises(RuntimeError, match=r"Database not initialized"),
    ):
        gen = db.get_db()
        await gen.__anext__()


async def test_init_db_postgresql_url_replacement():
    """Tests URL logic by mocking the SQLAlchemy engine creator."""
    original_url = "postgresql://user:pass@localhost/db"

    with patch("flash_db.db.create_async_engine") as mock_create:
        db.init_db(original_url)

        # Verify the string was swapped before being sent to SQLAlchemy
        called_url = mock_create.call_args[0][0]
        assert called_url == "postgresql+asyncpg://user:pass@localhost/db"


async def test_close_db_handles_none():
    """Tests closing when engine is already None."""
    with patch("flash_db.db._engine", None):
        # Should execute silently
        await db.close_db()


class TestQuerySet:
    async def test_queryset_is_lazy(self, db_session):
        """Verify that filtering doesn't hit the DB until fetch() is called."""
        # This shouldn't trigger SQL yet
        qs = Article.objects.filter(Article.title == "Lazy")
        assert qs._stmt is not None

        await create_article(db_session, title="Lazy")

        # Now execute
        results: Sequence[Article] = await qs.fetch(db_session)
        assert len(results) == 1

    async def test_queryset_limit_offset_order(self, db_session):
        """Verify pagination and ordering."""
        for i in range(5):
            await create_article(db_session, title=f"Article {i}")

        qs = Article.objects.all().order_by(Article.title.desc()).limit(2)
        results: Sequence[Article] = await qs.fetch(db_session)

        assert len(results) == 2
        assert results[0].title == "Article 4"
        assert results[1].title == "Article 3"

    async def test_queryset_count_and_exists(self, db_session):
        """Verify scalar execution methods."""
        await create_article(db_session, title="Visible")

        qs = Article.objects.filter(Article.title == "Visible")
        assert await qs.count(db_session) == 1
        assert await qs.exists(db_session) is True

        empty_qs = Article.objects.filter(Article.title == "Invisible")
        assert await empty_qs.exists(db_session) is False

    async def test_bulk_update_status_change(self, db_session):
        """Verify bulk update with filters."""
        # Setup: Create distinct titles that match a pattern
        await create_article(db_session, title="Draft: Article 1")
        await create_article(db_session, title="Draft: Article 2")
        await create_article(db_session, title="Final: Article 3")

        # Action: Update titles containing 'Draft'
        # This hits QuerySet.update() and its safety check for filters
        count = await Article.objects.filter(Article.title.contains("Draft")).update(
            db_session,
            content="Published Content",
        )

        # Assertions
        assert count == 2

        # Verify the update actually persisted
        updated_count = await Article.objects.filter(
            Article.content == "Published Content",
        ).count(db_session)
        assert updated_count == 2

    async def test_delete_safety_guardrail(self, db_session):
        """Verify that deleting without filters raises ValueError."""
        with pytest.raises(ValueError, match="Refusing to delete without filters"):
            await Article.objects.all().delete(db_session)

    async def test_bulk_delete_with_filter(self, db_session):
        """Verify filtered bulk deletion."""
        await create_article(db_session, title="Delete Me")
        await create_article(db_session, title="Keep Me")

        count = await Article.objects.filter(Article.title == "Delete Me").delete(
            db_session,
        )
        assert count == 1

        assert await Article.objects.all().count(db_session) == 1

    async def test_queryset_select_related_applies_joinedload(self, db_session):
        """Verify select_related adds relationship loading to the statement."""
        assert db_session
        qs = Article.objects.all().select_related("comments")
        assert "JOIN" in str(qs._stmt)

    async def test_queryset_update_raises_value_error_without_filter(self, db_session):
        """Verify bulk update refuses to run without a filter (Safety Guard)."""
        with pytest.raises(ValueError, match="Refusing to update without filters"):
            await Article.objects.all().update(db_session, title="New")

    async def test_queryset_update_raises_runtime_error_on_sqlalchemy_failure(self):
        """Verify bulk update raises SQLAlchemyError directly."""
        mock_db = AsyncMock()
        mock_db.execute.side_effect = SQLAlchemyError("Mocked Update Failure")
        qs = Article.objects.filter(Article.id == 1)

        with pytest.raises(SQLAlchemyError, match="Mocked Update Failure"):
            await qs.update(mock_db, title="New Title")

    async def test_queryset_delete_raises_runtime_error_on_sqlalchemy_failure(self):
        """Verify bulk delete raises SQLAlchemyError directly."""
        mock_db = AsyncMock()
        mock_db.execute.side_effect = SQLAlchemyError("Mocked Delete Failure")
        qs = Article.objects.filter(Article.id == 1)

        with pytest.raises(SQLAlchemyError, match="Mocked Delete Failure"):
            await qs.delete(mock_db)


class TestModelManager:
    async def test_create_and_get_by_pk(self, db_session):
        """Verify single record creation and PK retrieval."""
        article = await create_article(db_session, title="Manager Test")

        # Test get_by_pk
        fetched = await Article.objects.get_by_pk(db_session, article.id)
        assert fetched.title == "Manager Test"
        assert fetched.id == article.id

    async def test_get_with_conditions(self, db_session):
        """Verify retrieval using SQLAlchemy column conditions."""
        await create_article(db_session, title="Unique Title")

        fetched = await Article.objects.get(db_session, Article.title == "Unique Title")
        assert fetched.title == "Unique Title"

    async def test_get_raises_on_multiple_matches(self, db_session):
        """Verify get() raises ValueError when content is not unique."""
        # title must be unique, so keep them different
        await Article.objects.create(
            db_session,
            title="T1",
            content="Duplicate Content",
        )
        await Article.objects.create(
            db_session,
            title="T2",
            content="Duplicate Content",
        )

        with pytest.raises(ValueError, match="returned more than one"):
            await Article.objects.get(
                db_session,
                Article.content == "Duplicate Content",
            )

    async def test_update_single_record(self, db_session):
        """Verify the manager's atomic update method."""
        article = await create_article(db_session, title="Old Title")

        updated = await Article.objects.update(
            db_session,
            article.id,
            title="New Title",
        )
        assert updated.title == "New Title"

        # Verify persistence
        refresh = await Article.objects.get_by_pk(db_session, article.id)
        assert refresh.title == "New Title"

    async def test_delete_by_pk(self, db_session):
        """Verify deletion by primary key."""
        article = await create_article(db_session, title="To Delete")
        count = await Article.objects.delete_by_pk(db_session, article.id)
        assert count == 1

        # Verify it's deleted
        with pytest.raises(ValueError):
            await Article.objects.get_by_pk(db_session, article.id)

    async def test_delete_by_pk_not_found(self, db_session):
        """Verify delete_by_pk returns 0 when not found."""
        count = await Article.objects.delete_by_pk(db_session, 99999)
        assert count == 0

    async def test_delete_by_pk_raise_if_missing_branch(self, db_session):
        count = await Article.objects.delete_by_pk(
            db_session,
            999999,
            raise_if_missing=False,
        )
        assert count == 0

        with pytest.raises(ValueError, match="not found"):
            await Article.objects.delete_by_pk(
                db_session,
                999999,
                raise_if_missing=True,
            )

    async def test_queryset_first(self, db_session):
        """Verify queryset.first() returns first or None."""
        await create_article(db_session, title="First")
        await create_article(db_session, title="Second")

        first = await Article.objects.all().first(db_session)
        assert first
        assert first.title == "First"

        # Empty queryset
        empty_first = await Article.objects.filter(
            Article.title == "NonExistent",
        ).first(db_session)
        assert empty_first is None

    async def test_update_non_existent_id_raises_error(self, db_session):
        with pytest.raises(ValueError, match="Article with id 9999 not found"):
            await Article.objects.update(db_session, pk=9999, title="New Title")

    async def test_queryset_offset(self, db_session):
        with pytest.raises(ValueError, match="Article with id 99999 not found"):
            await Article.objects.update(db_session, pk=99999, title="New Title")

    async def test_delete_by_pk_foreign_key_violation(self, db_session):
        article = await Article.objects.create(
            db_session,
            title="Parent",
            content="...",
        )

        await Comment.objects.create(
            db_session,
            text="I depend on the article",
            article_id=article.id,
        )

        with pytest.raises(IntegrityError):
            await Article.objects.delete_by_pk(db_session, pk=article.id)

    async def test_update_statement_error_triggers_rollback(self, db_session):
        article = await create_article(db_session, title="Valid")

        # Passing an invalid type (dict) to a String column triggers ProgrammingError
        with pytest.raises(ProgrammingError):
            await Article.objects.update(
                db_session,
                article.id,
                title={"invalid": "type"},
            )

    async def test_update_raises_runtime_error_on_integrity_violation(self, db_session):
        """Verify update raises IntegrityError."""
        await Article.objects.create(db_session, title="Conflict")
        target = await Article.objects.create(db_session, title="Original")

        with pytest.raises(IntegrityError):
            await Article.objects.update(db_session, pk=target.id, title="Conflict")

    async def test_queryset_no_filter_conditions(self, db_session):
        """Verify filter() with no conditions returns same queryset."""
        await create_article(db_session, title="Test")
        qs = Article.objects.filter()
        results = await qs.fetch(db_session)
        assert len(results) > 0

    async def test_manager_update_not_found(self, db_session):
        """Verify manager.update raises ValueError when record not found."""
        with pytest.raises(ValueError, match="not found"):
            await Article.objects.update(db_session, 99999, title="New")

    async def test_db_initialization(self, db_session):
        """Verify database session works correctly."""
        article = await create_article(db_session, title="DB Test")
        assert article
        assert article.id
        assert article.created_at

    async def test_queryset_bulk_update_with_valid_filter(self, db_session):
        """Verify bulk update executes correctly."""
        await create_article(db_session, title="Original1")
        await create_article(db_session, title="Original2")

        count = await Article.objects.filter(
            Article.title.startswith("Original"),
        ).update(db_session, content="Updated content")
        assert count >= 2

    async def test_queryset_bulk_delete_count(self, db_session):
        """Verify bulk delete returns correct count."""
        await create_article(db_session, title="Delete1")
        await create_article(db_session, title="Delete2")

        count = await Article.objects.filter(Article.title.startswith("Delete")).delete(
            db_session,
        )
        assert count >= 2

    async def test_count_with_no_records(self, db_session):
        """Verify count returns 0 for empty result set."""
        count = await Article.objects.filter(
            Article.title == "NonExistentArticle",
        ).count(db_session)
        assert count == 0

    async def test_exists_returns_false_for_empty(self, db_session):
        """Verify exists returns False when no matches."""
        exists = await Article.objects.filter(
            Article.title == "NonExistentArticle",
        ).exists(db_session)
        assert exists is False

    async def test_filter_combining_equality_and_null_checks(self, db_session):
        """Verify filtering by both equality and NULL constraints."""
        # Titles MUST be unique now
        await Article.objects.create(
            db_session,
            title="Unique 1",
            content="Has Content",
        )
        await Article.objects.create(db_session, title="Unique 2", content=None)

        qs = Article.objects.filter(Article.content.is_not(None))
        results = await qs.fetch(db_session)

        assert len(results) == 1
        assert results[0].title == "Unique 1"


class TestErrorHandling:
    """Test error handling and edge cases."""

    async def test_queryset_error_on_update_without_filter(self, db_session):
        """Verify bulk update without filter raises error."""
        await create_article(db_session, title="Article")

        with pytest.raises(ValueError, match="Refusing to update without filters"):
            await Article.objects.all().update(db_session, title="Updated")

    async def test_queryset_error_on_delete_without_filter(self, db_session):
        """Verify bulk delete without filter raises error."""
        await create_article(db_session, title="Article")

        with pytest.raises(ValueError, match="Refusing to delete without filters"):
            await Article.objects.all().delete(db_session)

    async def test_get_raises_valueerror_if_no_match(self, db_session):
        """Verify get() raises ValueError when no records match."""
        with pytest.raises(ValueError, match="does not exist"):
            await Article.objects.get(db_session, Article.title == "NonExistent")


class TestQuerySetChaining:
    """Test QuerySet method chaining."""

    async def test_select_related_method(self, db_session):
        """Verify select_related method works (eager loading)."""
        await create_article(db_session, title="Article1")

        # select_related returns a QuerySet that can be further chained
        qs = Article.objects.all().select_related()
        results = await qs.fetch(db_session)
        assert len(results) > 0

    async def test_multiple_order_by(self, db_session):
        """Verify multiple order_by calls work correctly."""
        await create_article(db_session, title="Z Article")
        await create_article(db_session, title="A Article")

        qs = Article.objects.all().order_by(Article.title)
        results = await qs.fetch(db_session)
        assert results[0].title == "A Article"


class TestTimestampMixin:
    """Test TimestampMixin functionality."""

    async def test_created_at_is_set(self, db_session):
        """Verify created_at is automatically set."""
        article = await create_article(db_session, title="Timestamp Test")
        assert article.created_at

    async def test_updated_at_on_update(self, db_session):
        """Verify updated_at changes on update."""
        article = await create_article(db_session, title="Original")
        original_updated = article.updated_at

        updated = await Article.objects.update(db_session, article.id, title="Modified")
        assert updated.title == "Modified"
        assert original_updated != updated.updated_at


@pytest.mark.parametrize(
    "method_name, line_to_hit",
    [
        ("update", "SQLAlchemyError"),
        ("delete_by_pk", "SQLAlchemyError"),
        ("delete_by_pk", "GenericException"),
    ],
)
async def test_manager_error_handling_rollback(db_session, method_name, line_to_hit):
    """
    Forces the code to enter the 'except' blocks to ensure 100% coverage
    of rollback and raise logic.
    """
    # Ensure db_session fixture is properly initialized (even though we use mock)
    assert db_session

    # 1. Setup Mock
    mock_session = AsyncMock()

    if line_to_hit == "SQLAlchemyError":
        # Force a SQLAlchemy specific error
        mock_session.execute.side_effect = SQLAlchemyError("Mock DB Error")
    else:
        # Force a generic non-SQL error (like a bug in the driver)
        mock_session.execute.side_effect = Exception("Generic Crash")

    # 2. Execute & Verify
    manager = Article.objects

    expected_error = SQLAlchemyError if line_to_hit == "SQLAlchemyError" else Exception
    match_msg = "Mock DB Error" if line_to_hit == "SQLAlchemyError" else "Generic Crash"

    if method_name == "update":
        with pytest.raises(expected_error, match=match_msg):
            await manager.update(mock_session, pk=1, title="New")

    elif method_name == "delete_by_pk":
        with pytest.raises(expected_error, match=match_msg):
            await manager.delete_by_pk(mock_session, pk=1)
