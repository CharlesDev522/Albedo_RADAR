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
    default_subnet: int = 97
    poll_interval_seconds: int = 3
    metagraph_sync_interval_seconds: int = 60
    full_scan_interval_seconds: int = 300
    slot_scan_interval_seconds: int = 30
    mechid: int = 0

    # Primary dashboard subnet (SN97 Albedo)
    dashboard_subnets: list[int] = [97]
    coingecko_tao_price_url: str = "https://api.coingecko.com/api/v3/simple/price"
    taomarketcap_api_key: str | None = None
    taomarketcap_price_url: str | None = None
    taostats_api_key: str | None = None
    taostats_api_url: str = "https://api.taostats.io"
    market_price_cache_seconds: int = 60
    market_subnet_cache_seconds: int = 30
    market_http_timeout_seconds: float = 10.0

    # Albedo subnet dashboard (public Hippius JSON mirror)
    albedo_dashboard_url: str = "https://us-east-1.hippius.com/albedo"

    # Hippius registry repo tracking
    hippius_registry_url: str = "https://registry.hippius.com"
    hippius_hub_api_url: str = "https://api.hippius.com/api/models"
    hippius_hub_search_queries: list[str] = [
        "albedo",
        "albedo-qwen3.6-35b",
        "albedo-qwen3-4b",
    ]
    hippius_hub_page_size: int = 100
    hippius_hub_max_pages: int = 15
    huggingface_api_url: str = "https://huggingface.co/api"
    repo_track_interval_seconds: int = 60
    repo_track_revision: str = "main"
    priority_miner_namespaces: list[str] = [
        "cyantest",
        "booksome",
        "divinequest",
    ]
    priority_challenger_top_n: int = 10

    # Notifications (Slack)
    notifications_enabled: bool = True
    slack_webhook_url: str | None = None
    slack_channel: str | None = None
    slack_app_name: str = "Albedo_Notification"
    notification_reg_fee_threshold_tao: float = 0.75
    albedo_notification_poll_seconds: int = 15

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
