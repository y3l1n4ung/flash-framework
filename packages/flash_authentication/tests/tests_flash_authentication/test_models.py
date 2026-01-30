import pytest
from flash_authentication.models import User
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


class TestUser:
    """Tests for the concrete User model logic and fields (Unit Tests)."""

    def test_model_initialization(self):
        """
        Test initialization of the User model.
        """
        user = User(username="defaults_user", email="def@example.com")
        assert user.username == "defaults_user"
        assert user.email == "def@example.com"
        assert user.display_name == user.username
        # Defaults are None until flushed to DB
        assert user.is_active is None

    def test_explicit_initialization(self):
        user = User(username="admin", is_active=True, is_staff=True, is_superuser=True)
        assert user.is_active is True
        assert user.is_staff is True

    def test_email_nullability(self):
        user = User(username="no_email_user", email=None)
        assert user.email is None

    def test_password_hashing_flow(self):
        user = User(username="testuser", email="test@example.com")
        user.set_password("SecurePass123")
        assert user.password_hash is not None
        assert user.password_hash != "SecurePass123"
        assert user.check_password("SecurePass123") is True
        assert user.check_password("WrongPass") is False

    def test_string_representation(self):
        user = User(username="testuser", id=1)
        assert str(user) == "testuser"
        assert "User" in repr(user)


@pytest.mark.asyncio
class TestUserPersistence:
    """
    Tests requiring the Async Database Session.
    Verifies defaults, constraints, and persistence.
    """

    async def test_create_user_defaults(self, db_session):
        """Verify that DB applies defaults (is_active=True) upon insertion."""
        user = User(username="db_user", email="db@test.com")
        user.set_password("password")

        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        assert user.id is not None
        assert user.is_active is True  # Default applied
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.created_at is not None

    async def test_unique_username_constraint(self, db_session):
        """Verify that duplicate usernames raise IntegrityError."""
        user1 = User(username="unique_guy", email="u1@test.com")
        user1.set_password("pass")
        db_session.add(user1)
        await db_session.commit()

        user2 = User(username="unique_guy", email="u2@test.com")
        user2.set_password("pass")
        db_session.add(user2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_unique_email_constraint(self, db_session):
        """Verify that duplicate emails raise IntegrityError."""
        user1 = User(username="u1", email="shared@test.com")
        user1.set_password("pass")
        db_session.add(user1)
        await db_session.commit()

        user2 = User(username="u2", email="shared@test.com")
        user2.set_password("pass")
        db_session.add(user2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_fetch_user_by_username(self, db_session):
        """Test retrieving a user via select statement."""
        user = User(username="fetch_me", email="fetch@test.com")
        user.set_password("pass")
        db_session.add(user)
        await db_session.commit()

        # New Query
        stmt = select(User).where(User.username == "fetch_me")
        result = await db_session.execute(stmt)
        fetched_user = result.scalar_one_or_none()

        assert fetched_user is not None
        assert fetched_user.id == user.id
        assert fetched_user.email == "fetch@test.com"
