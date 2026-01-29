from datetime import datetime, timedelta, timezone

import pytest
from flash_authentication import User
from flash_authentication_session.models import UserSession
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_session(db_session: AsyncSession, test_user: User):
    """Test creating a session with default values."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)

    session = UserSession(
        user_id=test_user.id,
        ip_address="127.0.0.1",
        user_agent="TestAgent",
        expires_at=expires_at,
    )

    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    assert session.session_key is not None
    assert len(session.session_key) > 0
    assert session.user_id == test_user.id
    assert session.created_at is not None
    assert session.is_expired is False


@pytest.mark.asyncio
async def test_session_is_expired_future(test_user):
    """Test is_expired property for a future date."""
    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    session = UserSession(user_id=test_user.id, expires_at=future_time)
    assert session.is_expired is False


@pytest.mark.asyncio
async def test_session_is_expired_past(test_user):
    """Test is_expired property for a past date."""
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)
    session = UserSession(user_id=test_user.id, expires_at=past_time)
    assert session.is_expired is True


@pytest.mark.asyncio
async def test_session_relationship_persistence(db_session: AsyncSession, test_user):
    """Ensure the session retrieves the correct user from DB."""
    expires = datetime.now(timezone.utc) + timedelta(days=1)
    session = UserSession(user_id=test_user.id, expires_at=expires)

    db_session.add(session)
    await db_session.commit()

    await db_session.refresh(session)

    stmt = select(UserSession).where(UserSession.session_key == session.session_key)
    result = await db_session.scalar(stmt)

    assert result is not None
    assert result.user_id == test_user.id
