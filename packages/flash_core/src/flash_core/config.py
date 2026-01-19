"""
Foundation settings for the Flash ecosystem.
"""

from typing import Literal
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FlashSettings(BaseSettings):
    """
    Core settings for all Flash modules.
    Individual packages (like flash_admin) should inherit from this.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    # --- Basic Environment ---
    DEBUG: bool = True
    SECRET_KEY: str = ""
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"

    # --- Unified Pagination & API Limits ---
    # These power your PaginationParams in parameter.py
    DEFAULT_LIST_PER_PAGE: int = 50
    MAX_API_LIMIT: int = 500
    MIN_LIST_PER_PAGE: int = 1

    # --- Security Fundamentals ---
    # Core auth settings shared by flash_authentication and flash_rest_framework
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Database Core ---
    DATABASE_URL: str | None = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Redis / Cache Infrastructure ---
    REDIS_URL: str | None = None
    CACHE_DEFAULT_TTL: int = 300

    # --- Feature Flags ---
    ENABLE_REQUEST_ID: bool = True
    ENABLE_TIMING_METRICS: bool = True
    ENABLE_CORS: bool = False

    @model_validator(mode="after")
    def validate_security(self) -> "FlashSettings":
        """Ensures production doesn't ship without a secret key."""
        if not self.DEBUG and not self.SECRET_KEY:
            raise ValueError("SECRET_KEY is mandatory in production mode.")
        return self

    def is_development(self) -> bool:
        return self.DEBUG or self.ENVIRONMENT == "development"


# Singleton instance for core use
flash_settings = FlashSettings()
