"""Continuous v5 commitment poller for subnet 97."""

from __future__ import annotations

import asyncio
import logging
import signal

from bittensor.core.async_subtensor import AsyncSubtensor

from app.chain_reader.commitment_scanner import scan_v5_commitments
from app.collectors.event_publisher import EventPublisher
from app.collectors.subtensor_client import SubtensorClient
from app.config import get_settings
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal, engine
from app.processing.commitment_state_builder import CommitmentStateBuilder

logger = logging.getLogger(__name__)


class CommitmentPoller:
    """Polls RevealedCommitments on-chain and tracks latest v5 commits per miner."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.subtensor_client = SubtensorClient(self.settings)
        self._subtensor: AsyncSubtensor | None = None
        self.publisher = EventPublisher(self.settings)
        self.state_builder = CommitmentStateBuilder(publisher=self.publisher)
        self._running = False

    async def setup(self) -> None:
        await init_db(engine)
        await self.subtensor_client.connect()
        self._subtensor = self.subtensor_client._subtensor
        await self.publisher.connect()
        logger.info(
            "Commitment poller ready — netuid=%d network=%s",
            self.settings.default_subnet,
            self.settings.bittensor_network,
        )

    async def teardown(self) -> None:
        await self.subtensor_client.disconnect()
        await self.publisher.disconnect()
        await engine.dispose()

    async def poll_once(self, netuid: int | None = None) -> dict[str, int]:
        netuid = netuid or self.settings.default_subnet
        assert self._subtensor is not None

        commits = await scan_v5_commitments(self._subtensor, netuid)
        snapshot = await self.subtensor_client.get_subnet_snapshot(netuid)

        async with AsyncSessionLocal() as session:
            stats = await self.state_builder.process_commits(session, commits, snapshot)
            await session.commit()

        logger.info(
            "Commitment poll netuid=%d v5_commits=%d new=%d updated=%d unchanged=%d events=%d",
            netuid,
            len(commits),
            stats["new"],
            stats["updated"],
            stats["unchanged"],
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
                logger.exception("Commitment poll failed")
            await asyncio.sleep(self.settings.poll_interval_seconds)

    def stop(self) -> None:
        self._running = False


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    poller = CommitmentPoller()
    loop = asyncio.get_event_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, poller.stop)

    try:
        await poller.run()
    finally:
        await poller.teardown()


if __name__ == "__main__":
    asyncio.run(main())
