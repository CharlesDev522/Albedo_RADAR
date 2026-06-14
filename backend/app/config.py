"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "MinerWatch"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Bittensor / Subtensor
    bittensor_network: str = "finney"
    default_subnet: int = 1
    poll_interval_seconds: int = 30
    mechid: int = 0

    # Database
    database_url: str = "postgresql+asyncpg://minerwatch:minerwatch@localhost:5432/minerwatch"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Kafka (optional event stream)
    kafka_enabled: bool = False
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "minerwatch.events"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
