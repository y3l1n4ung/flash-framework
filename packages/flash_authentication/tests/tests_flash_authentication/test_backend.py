from unittest.mock import MagicMock

import pytest
from flash_authentication import (
    AnonymousUser,
    AuthenticationBackend,
    AuthenticationResult,
)

# Shared mock result for consistency
MOCK_RESULT = AuthenticationResult(
    success=False,
    user=AnonymousUser(),
    message="Fail To Authenticate",
)


class ConcreteBackend(AuthenticationBackend):
    """A valid implementation for testing the contract."""

    async def authenticate(self, *_args, **_kwargs) -> AuthenticationResult:
        return MOCK_RESULT

    async def login(self, *_args, **_kwargs) -> AuthenticationResult:
        return MOCK_RESULT

    async def logout(self, *_args, **_kwargs) -> str:
        return "Logged Out"


@pytest.fixture
def backend():
    return ConcreteBackend()


@pytest.fixture
def mock_request():
    return MagicMock()


class TestAuthenticationBackend:
    @pytest.mark.asyncio
    async def test_login_returns_correct_type(self, backend, mock_request):
        """Ensure login adheres to the return type contract."""
        result = await backend.login(mock_request, extra_data="test")
        assert isinstance(result, AuthenticationResult)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_logout_functionality(self, backend: ConcreteBackend, mock_request):
        """Verify logout executes and returns expected value."""
        response = await backend.logout(mock_request)
        assert response == "Logged Out"

    @pytest.mark.asyncio
    async def test_authenticate_with_unpack_params(self, backend):
        """Verify authenticate handles variable keyword arguments."""

        result = await backend.authenticate(token="abc-123", provider="google")
        assert result == MOCK_RESULT
