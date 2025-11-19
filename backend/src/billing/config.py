"""Application configuration using pydantic-settings."""
from typing import List

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # Database Configuration
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/billing",
        description="PostgreSQL connection string with asyncpg driver",
    )

    # Redis Configuration
    redis_url: RedisDsn = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string for caching and sessions",
    )

    arq_redis_url: RedisDsn = Field(
        default="redis://localhost:6379/1",
        description="Redis connection string for ARQ background workers",
    )

    # Stripe Configuration
    stripe_secret_key: str = Field(
        default="sk_test_placeholder",
        description="Stripe secret key for API authentication",
    )
    stripe_webhook_secret: str = Field(
        default="whsec_placeholder",
        description="Stripe webhook signature verification secret",
    )
    stripe_publishable_key: str = Field(
        default="pk_test_placeholder",
        description="Stripe publishable key for client-side integrations",
    )

    # Application Configuration
    app_env: str = Field(default="development", description="Application environment (development/staging/production)")
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=True, description="Enable debug mode")
    secret_key: str = Field(
        default="change-this-secret-key-in-production",
        description="Application secret key for encryption",
    )

    # JWT Configuration
    jwt_secret_key: str = Field(
        default="change-this-jwt-secret-in-production",
        description="JWT signing key",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    access_token_expire_minutes: int = Field(default=30, description="JWT token expiration time in minutes")

    # CORS Configuration
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins",
    )

    # Rate Limiting
    rate_limit_per_hour: int = Field(default=1000, description="Rate limit per hour per API key")

    # Observability
    otel_service_name: str = Field(default="billing-api", description="OpenTelemetry service name")
    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4318",
        description="OTLP exporter endpoint",
    )

    # Company/Branding Configuration
    company_name: str = Field(default="Your Company", description="Company name for invoices")
    logo_url: str = Field(default="", description="Company logo URL for invoices")
    brand_primary_color: str = Field(default="#000000", description="Primary brand color")
    brand_secondary_color: str = Field(default="#FFFFFF", description="Secondary brand color")


# Global settings instance
settings = Settings()
