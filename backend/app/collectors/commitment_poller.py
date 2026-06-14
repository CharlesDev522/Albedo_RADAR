"""Continuous v5 commitment poller — fast active scan + periodic full sync."""

from __future__ import annotations

import asyncio
import logging
import signal
import time

from bittensor.core.async_subtensor import AsyncSubtensor

from app.chain_reader.commitment_scanner import (
    _neuron_index,
    scan_v5_active_fast,
    scan_v5_commitments,
)
from app.collectors.event_publisher import EventPublisher
from app.collectors.subtensor_client import SubtensorClient
from app.config import get_settings
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal, engine
from app.processing.commitment_state_builder import CommitmentStateBuilder

logger = logging.getLogger(__name__)


class CommitmentPoller:
    """Dual-speed poller: fast CommitmentOf every few seconds, full sync periodically."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.subtensor_client = SubtensorClient(self.settings)
        self._subtensor: AsyncSubtensor | None = None
        self.publisher = EventPublisher(self.settings)
        self.state_builder = CommitmentStateBuilder(publisher=self.publisher)
        self._running = False
        self._neurons: dict[str, dict] = {}
        self._last_full_scan = 0.0
        self._last_metagraph_sync = 0.0

    async def setup(self) -> None:
        await init_db(engine)
        await self.subtensor_client.connect()
        self._subtensor = self.subtensor_client._subtensor
        await self.publisher.connect()
        netuid = self.settings.default_subnet
        self._neurons = await _neuron_index(self._subtensor, netuid)
        logger.info(
            "Commitment poller ready — netuid=%d fast=%ds metagraph=%ds full=%ds neurons=%d",
            netuid,
            self.settings.poll_interval_seconds,
            self.settings.metagraph_sync_interval_seconds,
            self.settings.full_scan_interval_seconds,
            len(self._neurons),
        )
        # Initial full sync
        await self._full_poll(netuid)

    async def teardown(self) -> None:
        await self.subtensor_client.disconnect()
        await self.publisher.disconnect()
        await engine.dispose()

    async def _fast_poll(self, netuid: int) -> dict[str, int]:
        """~1-2s: scan CommitmentOf only, detect new v5 commits instantly."""
        assert self._subtensor is not None
        t0 = time.monotonic()
        commits = await scan_v5_active_fast(self._subtensor, netuid, self._neurons)

        async with AsyncSessionLocal() as session:
            stats = await self.state_builder.process_commits(session, commits, snapshot=None)
            await session.commit()

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if stats["new"] or stats["updated"]:
            logger.info(
                "FAST netuid=%d +%d new, +%d updated in %dms (v5_total=%d)",
                netuid,
                stats["new"],
                stats["updated"],
                elapsed_ms,
                len(commits),
            )
        else:
            logger.debug("fast poll %dms v5=%d unchanged", elapsed_ms, len(commits))
        return stats

    async def _full_poll(self, netuid: int) -> dict[str, int]:
        """Full scan: revealed history + metagraph registry sync."""
        assert self._subtensor is not None
        t0 = time.monotonic()
        self._neurons = await _neuron_index(self._subtensor, netuid)
        self._last_metagraph_sync = time.monotonic()

        commits = await scan_v5_commitments(self._subtensor, netuid)
        snapshot = await self.subtensor_client.get_subnet_snapshot(netuid)

        async with AsyncSessionLocal() as session:
            stats = await self.state_builder.process_commits(session, commits, snapshot)
            await session.commit()

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "FULL netuid=%d v5=%d new=%d updated=%d in %dms",
            netuid,
            len(commits),
            stats["new"],
            stats["updated"],
            elapsed_ms,
        )
        self._last_full_scan = time.monotonic()
        return stats

    async def poll_once(self, netuid: int | None = None) -> dict[str, int]:
        netuid = netuid or self.settings.default_subnet
        now = time.monotonic()

        if now - self._last_metagraph_sync >= self.settings.metagraph_sync_interval_seconds:
            self._neurons = await _neuron_index(self._subtensor, netuid)
            self._last_metagraph_sync = now

        if now - self._last_full_scan >= self.settings.full_scan_interval_seconds:
            return await self._full_poll(netuid)

        return await self._fast_poll(netuid)

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
