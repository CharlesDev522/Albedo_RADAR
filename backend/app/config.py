"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _coerce_reg_fee_thresholds_env(v: object) -> str:
    if isinstance(v, (list, tuple)):
        return ",".join(str(x) for x in v)
    if v is None:
        return "1.0,0.75,0.6"
    return str(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "MinerWatch"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # Bittensor / Subtensor
    bittensor_network: str = "finney"
    default_subnet: int = 97
    poll_interval_seconds: int = 2
    metagraph_sync_interval_seconds: int = 45
    full_scan_interval_seconds: int = 300
    slot_scan_interval_seconds: int = 15
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
    # Optional JSON file with pre-v13 coronations (v1–v12 etc.) — see data/albedo_crown_seed_sn97.example.json
    albedo_crown_seed_path: str | None = None

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
    # Comma-separated in .env e.g. 1.0,0.75,0.6 (must be str — list type breaks pydantic env JSON parse).
    notification_reg_fee_thresholds_tao: Annotated[
        str, BeforeValidator(_coerce_reg_fee_thresholds_env)
    ] = "1.0,0.75,0.6"
    albedo_notification_poll_seconds: int = 1
    notification_reg_fee_poll_seconds: int = 30
    notification_http_timeout_seconds: float = 8.0
    # Silence Slack after fresh docker up until grace elapses AND initial sync completes.
    notification_grace_seconds: int = 300
    # Lightweight Hippius hub HTTP fetches during startup (no DB). 0 = skip this gate.
    notification_min_hub_index_probes: int = 0
    # Go LIVE anyway after this many seconds from collector start (grace + full scan).
    notification_startup_max_seconds: int = 600
    # Opt-in only: skip grace + sync gates (instant live). Default keeps grace on every start.
    notification_skip_startup_grace: bool = False

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

    def reg_fee_thresholds_list(self) -> list[float]:
        from app.notifications.reg_fee_tiers import normalize_reg_fee_thresholds

        return normalize_reg_fee_thresholds(self.notification_reg_fee_thresholds_tao)


@lru_cache
def get_settings() -> Settings:
    return Settings()
