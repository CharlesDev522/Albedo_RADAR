"""Continuous v6 commitment poller — fast active scan + periodic full sync."""

from __future__ import annotations

import asyncio
import logging
import signal
import time

from bittensor.core.async_subtensor import AsyncSubtensor

from app.chain_reader.commitment_scanner import (
    _neuron_index,
    scan_v6_active_fast,
    scan_v6_commitments,
)
from app.chain_reader.encrypted_commitment_scanner import scan_encrypted_commitments
from app.chain_reader.slot_commitment_scanner import scan_slot_statuses
from app.collectors.event_publisher import EventPublisher
from app.collectors.subtensor_client import SubtensorClient
from app.config import get_settings
from app.db.init_db import init_db
from app.db.models import Miner, MinerCommitment, MinerStatus
from app.db.session import AsyncSessionLocal, engine
from app.processing.commitment_state_builder import CommitmentStateBuilder
from app.processing.encrypted_commitment_state_builder import EncryptedCommitmentStateBuilder
from app.processing.slot_status_builder import SlotStatusBuilder
from sqlalchemy import func, select

logger = logging.getLogger(__name__)


class CommitmentPoller:
    """Dual-speed poller: fast CommitmentOf every few seconds, full sync periodically."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.subtensor_client = SubtensorClient(self.settings)
        self._subtensor: AsyncSubtensor | None = None
        self.publisher = EventPublisher(self.settings)
        self.state_builder = CommitmentStateBuilder(publisher=self.publisher)
        self.encrypted_state_builder = EncryptedCommitmentStateBuilder()
        self.slot_status_builder = SlotStatusBuilder()
        self._running = False
        self._neurons: dict[str, dict] = {}
        self._last_full_scan = 0.0
        self._last_metagraph_sync = 0.0
        self._poll_lock = asyncio.Lock()
        self._seen_v6_hotkeys: set[str] = set()

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
        try:
            await self._full_poll(netuid)
        except Exception:
            logger.exception("Initial full poll failed — falling back to fast poll")
            self._last_full_scan = time.monotonic()
            await self._fast_poll(netuid)
        await self._encrypted_poll(netuid)
        await self._slot_poll(netuid)

    async def _slot_poll(self, netuid: int) -> dict[str, int]:
        """Full per-UID slot map — v6, json, encrypted, none."""
        assert self._subtensor is not None
        slots = await scan_slot_statuses(self._subtensor, netuid, self._neurons)
        async with AsyncSessionLocal() as session:
            stats = await self.slot_status_builder.process_slots(session, slots, netuid)
            await session.commit()
        logger.info(
            "SLOTS netuid=%d total=%d updated=%d unchanged=%d",
            netuid,
            len(slots),
            stats["updated"],
            stats["unchanged"],
        )
        return stats

    async def teardown(self) -> None:
        await self.subtensor_client.disconnect()
        await self.publisher.disconnect()
        await engine.dispose()

    async def _sync_miners_from_cache(self, netuid: int, commits: list) -> None:
        """Ensure miner rows exist for committed hotkeys (fast path, no full metagraph)."""
        if not commits:
            return
        async with AsyncSessionLocal() as session:
            for c in commits:
                if c.uid is None:
                    continue
                result = await session.execute(
                    select(Miner).where(Miner.subnet == netuid, Miner.uid == c.uid)
                )
                miner = result.scalar_one_or_none()
                if miner is None:
                    session.add(
                        Miner(
                            uid=c.uid,
                            hotkey=c.hotkey,
                            coldkey=c.coldkey or "",
                            subnet=netuid,
                            registered_at_block=c.registered_at_block,
                            status=MinerStatus.ACTIVE,
                        )
                    )
                else:
                    miner.hotkey = c.hotkey
                    miner.coldkey = c.coldkey or miner.coldkey
                    miner.status = MinerStatus.ACTIVE
            await session.commit()

    async def _fast_poll(self, netuid: int) -> dict[str, int]:
        """~1-2s: scan CommitmentOf only, detect new v6 commits instantly."""
        assert self._subtensor is not None
        t0 = time.monotonic()
        commits = await scan_v6_active_fast(self._subtensor, netuid, self._neurons)

        new_hotkeys = {c.hotkey for c in commits} - self._seen_v6_hotkeys
        needs_neuron_refresh = any(c.uid is None for c in commits) or bool(new_hotkeys)
        if needs_neuron_refresh:
            self._neurons = await _neuron_index(self._subtensor, netuid)
            commits = await scan_v6_active_fast(self._subtensor, netuid, self._neurons)

        async with AsyncSessionLocal() as session:
            stats = await self.state_builder.process_commits(session, commits, snapshot=None)
            db_count = (
                await session.execute(
                    select(func.count())
                    .select_from(MinerCommitment)
                    .where(MinerCommitment.subnet == netuid, MinerCommitment.version == "v6")
                )
            ).scalar() or 0
            await session.commit()

        self._seen_v6_hotkeys = {c.hotkey for c in commits}
        await self._sync_miners_from_cache(netuid, commits)

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if stats["new"] > 0:
            logger.warning(
                "NEW v6 commit(s) netuid=%d count=%d uids=%s",
                netuid,
                stats["new"],
                sorted({c.uid for c in commits if c.uid is not None}),
            )
        logger.info(
            "FAST netuid=%d v6=%d new=%d updated=%d unchanged=%d db=%d %dms uids=%s",
            netuid,
            len(commits),
            stats["new"],
            stats["updated"],
            stats["unchanged"],
            db_count,
            elapsed_ms,
            sorted({c.uid for c in commits if c.uid is not None}),
        )

        if len(commits) > db_count:
            logger.warning(
                "on-chain ahead of DB (chain=%d db=%d) — running full scan",
                len(commits),
                db_count,
            )
            return await self._full_poll(netuid)

        return stats

    async def _encrypted_poll(self, netuid: int) -> dict[str, int]:
        """Scan CommitmentOf for TimelockEncrypted (pre-reveal ciphertext)."""
        assert self._subtensor is not None
        commits = await scan_encrypted_commitments(self._subtensor, netuid, self._neurons)

        if any(c.uid is None for c in commits):
            self._neurons = await _neuron_index(self._subtensor, netuid)
            commits = await scan_encrypted_commitments(self._subtensor, netuid, self._neurons)

        async with AsyncSessionLocal() as session:
            stats = await self.encrypted_state_builder.process_commits(session, commits, netuid)
            await session.commit()

        if stats["new"] > 0 or stats["updated"] > 0:
            logger.warning(
                "ENCRYPTED netuid=%d pending=%d new=%d updated=%d revealed=%d uids=%s",
                netuid,
                len(commits),
                stats["new"],
                stats["updated"],
                stats["revealed"],
                sorted({c.uid for c in commits if c.uid is not None}),
            )
        elif commits:
            logger.info(
                "ENCRYPTED netuid=%d pending=%d unchanged uids=%s",
                netuid,
                len(commits),
                sorted({c.uid for c in commits if c.uid is not None}),
            )
        return stats

    async def _full_poll(self, netuid: int) -> dict[str, int]:
        """Full scan: revealed history + metagraph registry sync."""
        assert self._subtensor is not None
        t0 = time.monotonic()
        self._neurons = await _neuron_index(self._subtensor, netuid)
        self._last_metagraph_sync = time.monotonic()

        commits = await scan_v6_commitments(self._subtensor, netuid)
        snapshot = await self.subtensor_client.get_subnet_snapshot(netuid)

        async with AsyncSessionLocal() as session:
            stats = await self.state_builder.process_commits(session, commits, snapshot)
            await session.commit()

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "FULL netuid=%d v6=%d new=%d updated=%d unchanged=%d %dms uids=%s",
            netuid,
            len(commits),
            stats["new"],
            stats["updated"],
            stats.get("unchanged", 0),
            elapsed_ms,
            sorted({c.uid for c in commits if c.uid is not None}),
        )
        self._last_full_scan = time.monotonic()
        return stats

    async def poll_once(self, netuid: int | None = None) -> dict[str, int]:
        netuid = netuid or self.settings.default_subnet
        async with self._poll_lock:
            now = time.monotonic()

            if now - self._last_metagraph_sync >= self.settings.metagraph_sync_interval_seconds:
                self._neurons = await _neuron_index(self._subtensor, netuid)
                self._last_metagraph_sync = now

            if now - self._last_full_scan >= self.settings.full_scan_interval_seconds:
                stats = await self._full_poll(netuid)
            else:
                stats = await self._fast_poll(netuid)

            await self._encrypted_poll(netuid)
            await self._slot_poll(netuid)
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
