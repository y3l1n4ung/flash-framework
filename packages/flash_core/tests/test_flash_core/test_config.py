import pytest
from flash_core import FlashSettings


class TestFlashSettings:
    def test_default_development_state(self):
        """Verify that by default, settings are in development mode."""
        settings = FlashSettings()
        assert settings.DEBUG is True
        assert settings.ENVIRONMENT == "development"
        assert settings.is_development() is True

    def test_is_development_logic(self):
        """Test the different combinations of DEBUG and ENVIRONMENT."""
        # Case 1: Debug True (Always dev mode)
        assert FlashSettings(DEBUG=True).is_development() is True

        # Case 2: Debug False, Env Development
        # Must provide SECRET_KEY because DEBUG is False
        assert (
            FlashSettings(
                DEBUG=False,
                ENVIRONMENT="development",
                SECRET_KEY="test_key",
            ).is_development()
            is True
        )

        # Case 3: Debug False, Env Production (True Production)
        assert (
            FlashSettings(
                DEBUG=False,
                ENVIRONMENT="production",
                SECRET_KEY="test_key",
            ).is_development()
            is False
        )

    def test_validate_security_production_success(self):
        """Ensures validator passes when SECRET_KEY is provided in production."""
        settings = FlashSettings(
            DEBUG=False,
            ENVIRONMENT="production",
            SECRET_KEY="super-secret-key",
        )
        assert settings.SECRET_KEY == "super-secret-key"

    def test_validate_security_production_failure(self):
        """Ensures ValueError is raised if SECRET_KEY is missing in production."""
        with pytest.raises(
            ValueError,
            match="SECRET_KEY is mandatory in production mode",
        ):
            FlashSettings(DEBUG=False, ENVIRONMENT="production", SECRET_KEY="")

    def test_env_variable_overrides(self, monkeypatch):
        """Verify that actual environment variables override the defaults."""
        monkeypatch.setenv("MAX_API_LIMIT", "1000")
        monkeypatch.setenv("ENABLE_CORS", "True")

        settings = FlashSettings()
        assert settings.MAX_API_LIMIT == 1000
        assert settings.ENABLE_CORS is True

    def test_singleton_instance(self):
        """Ensure the exported flash_settings is an instance of FlashSettings."""
        from flash_core.config import flash_settings

        assert isinstance(flash_settings, FlashSettings)
