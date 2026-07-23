"""Metagraph polling collector service."""

from __future__ import annotations

import asyncio
import logging
import signal

from app.collectors.event_publisher import EventPublisher
from app.collectors.subtensor_client import SubtensorClient
from app.config import get_settings
from app.db.session import AsyncSessionLocal, engine
from app.db.models import Base
from app.processing.miner_state_builder import MinerStateBuilder

logger = logging.getLogger(__name__)


class MetagraphPoller:
    """Continuously polls subtensor metagraph and processes state changes."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.subtensor = SubtensorClient(self.settings)
        self.publisher = EventPublisher(self.settings)
        self.state_builder = MinerStateBuilder(publisher=self.publisher)
        self._running = False

    async def setup(self) -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await self.subtensor.connect()
        await self.publisher.connect()
        logger.info("Metagraph poller initialized for subnet %d", self.settings.default_subnet)

    async def teardown(self) -> None:
        await self.subtensor.disconnect()
        await self.publisher.disconnect()
        await engine.dispose()

    async def poll_once(self, netuid: int | None = None) -> dict[str, int]:
        netuid = netuid or self.settings.default_subnet
        snapshot = await self.subtensor.get_subnet_snapshot(netuid)

        async with AsyncSessionLocal() as session:
            stats = await self.state_builder.process_snapshot(session, snapshot)
            await session.commit()

        logger.info(
            "Poll complete subnet=%d block=%d new=%d updated=%d deregistered=%d events=%d",
            snapshot.subnet,
            snapshot.block,
            stats["new"],
            stats["updated"],
            stats["deregistered"],
            stats["events"],
        )
        return stats

    async def run(self) -> None:
        self._running = True
        await self.setup()

        while self._running:
            try:
                await self.poll_once()
            except Exception:
                logger.exception("Poll cycle failed")
            await asyncio.sleep(self.settings.poll_interval_seconds)

    def stop(self) -> None:
        self._running = False


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    poller = MetagraphPoller()
    loop = asyncio.get_event_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, poller.stop)

    try:
        await poller.run()
    finally:
        await poller.teardown()


if __name__ == "__main__":
    asyncio.run(main())
