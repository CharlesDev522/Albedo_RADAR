"""Event stream publisher (Redis / optional Kafka)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from app.config import Settings

logger = logging.getLogger(__name__)


class EventPublisher:
    """Publishes miner events to Redis streams and optionally Kafka."""

    STREAM_KEY = "minerwatch:events"
    LIVE_CHANNEL = "minerwatch:live"
    STATE_KEY = "minerwatch:commit_state"
    STATE_KEY_PREFIX = "minerwatch:commit_state:"

    def state_key_for_subnet(self, subnet: int) -> str:
        return f"{self.STATE_KEY_PREFIX}{subnet}"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._redis: aioredis.Redis | None = None
        self._kafka_producer: Any = None

    async def connect(self) -> None:
        self._redis = aioredis.from_url(self.settings.redis_url, decode_responses=True)
        if self.settings.kafka_enabled:
            try:
                from aiokafka import AIOKafkaProducer

                self._kafka_producer = AIOKafkaProducer(
                    bootstrap_servers=self.settings.kafka_bootstrap_servers,
                    value_serializer=lambda v: json.dumps(v).encode(),
                )
                await self._kafka_producer.start()
                logger.info("Kafka producer connected")
            except Exception:
                logger.warning("Kafka unavailable, using Redis only", exc_info=True)

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.close()
        if self._kafka_producer:
            await self._kafka_producer.stop()

    async def publish(self, event_type: str, subnet: int, data: dict[str, Any]) -> None:
        payload = {
            "event_type": event_type,
            "subnet": subnet,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if self._redis:
            await self._redis.xadd(
                self.STREAM_KEY,
                {"payload": json.dumps(payload)},
                maxlen=100_000,
                approximate=True,
            )

        if self._kafka_producer:
            await self._kafka_producer.send_and_wait(self.settings.kafka_topic, payload)

        logger.debug("Published event: %s subnet=%d", event_type, subnet)

    async def publish_live(self, payload: dict[str, Any]) -> None:
        """Instant push to connected dashboards via Redis pub/sub."""
        if not self._redis:
            return
        message = json.dumps(payload, separators=(",", ":"))
        await self._redis.publish(self.LIVE_CHANNEL, message)
        subnet = payload.get("subnet")
        if subnet is not None:
            await self._redis.set(self.state_key_for_subnet(int(subnet)), message, ex=3600)
        await self._redis.set(self.STATE_KEY, message, ex=3600)
