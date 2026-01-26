import pytest
from flash_authentication.interface import BaseAuthenticator, BaseLoginBackend, BaseUser


class TestInterfaces:
    """
    Tests for Abstract Base Classes in interface.py.
    """

    def test_valid_concrete_implementation(self):
        """Verify that a fully compliant subclass works correctly."""

        class ConcreteUser(BaseUser):
            @property
            def username(self):
                return "user"

            @property
            def email(self):
                return "test@test.com"

            @property
            def is_authenticated(self):
                return True

            @property
            def is_active(self):
                return True

            @property
            def is_staff(self):
                return False

            @property
            def is_superuser(self):
                return False

            @property
            def display_name(self):
                return "Display Name"

        user = ConcreteUser()
        assert user.is_authenticated is True
        assert user.display_name == "Display Name"

    @pytest.mark.asyncio
    async def test_authenticator_contract(self):
        """Verify BaseAuthenticator interface."""

        class ConcreteAuth(BaseAuthenticator):
            async def authenticate(self, **kwargs):
                return "User"

        auth = ConcreteAuth()
        assert await auth.authenticate() == "User"

    @pytest.mark.asyncio
    async def test_login_backend_contract(self):
        """Verify BaseLoginBackend interface."""

        class ConcreteBackend(BaseLoginBackend):
            async def login(self, request, **kwargs):
                return "Logged In"

            async def logout(self, request, **kwargs):
                return "Logged Out"

        backend = ConcreteBackend()
        assert await backend.login(None) == "Logged In"
        assert await backend.logout(None) == "Logged Out"
