import pytest

from .models import Job

pytestmark = pytest.mark.asyncio


class TestSpecialTypes:
    """Tests for specialized column types like UUID."""

    async def test_uuid_primary_key_creation_and_retrieval(self, db_session):
        """Should support models where the primary key is a UUID."""
        job = await Job.objects.create(db_session, title="UUID Task")

        # Verify it can be fetched by its UUID primary key
        fetched = await Job.objects.get_by_pk(db_session, job.id)
        assert fetched.id == job.id
        assert fetched.title == "UUID Task"
