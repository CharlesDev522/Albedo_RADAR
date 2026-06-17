"""Continuous v6 commitment poller — single chain snapshot per cycle."""

from __future__ import annotations

import asyncio
import logging
import signal
import time

from bittensor.core.async_subtensor import AsyncSubtensor

from app.chain_reader.chain_snapshot import ChainSnapshot, load_chain_snapshot
from app.chain_reader.commitment_scanner import (
    _neuron_index,
    scan_v6_active_fast,
    scan_v6_from_snapshot,
    timelock_hotkeys_from_map,
)
from app.chain_reader.encrypted_commitment_scanner import scan_encrypted_from_map
from app.chain_reader.slot_commitment_scanner import scan_slots_from_snapshot
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
    """One chain snapshot per cycle; revealed history merged every poll for fresh commits."""

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
        self._last_slot_scan = 0.0
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
            "Commitment poller ready — netuid=%d fast=%ds slot=%ds metagraph=%ds full=%ds neurons=%d",
            netuid,
            self.settings.poll_interval_seconds,
            self.settings.slot_scan_interval_seconds,
            self.settings.metagraph_sync_interval_seconds,
            self.settings.full_scan_interval_seconds,
            len(self._neurons),
        )
        try:
            await self.poll_once(netuid)
        except Exception:
            logger.exception("Initial poll failed")

    async def _slot_poll(self, netuid: int, snapshot: ChainSnapshot) -> dict[str, int]:
        assert self._subtensor is not None
        slots = scan_slots_from_snapshot(snapshot, self._neurons)
        active_uids = {int(info["uid"]) for info in self._neurons.values()}
        async with AsyncSessionLocal() as session:
            stats = await self.slot_status_builder.process_slots(session, slots, netuid)
            pruned = await self.slot_status_builder.prune_absent_uids(session, netuid, active_uids)
            await session.commit()
        logger.info(
            "SLOTS netuid=%d total=%d updated=%d unchanged=%d pruned=%d",
            netuid,
            len(slots),
            stats["updated"],
            stats["unchanged"],
            pruned,
        )
        return stats

    async def teardown(self) -> None:
        await self.subtensor_client.disconnect()
        await self.publisher.disconnect()
        await engine.dispose()

    async def _sync_miners_from_cache(self, netuid: int, commits: list) -> None:
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

    async def _fast_poll(self, netuid: int, snapshot: ChainSnapshot) -> dict[str, int]:
        assert self._subtensor is not None
        t0 = time.monotonic()
        commits = await scan_v6_active_fast(
            self._subtensor, netuid, self._neurons, snapshot=snapshot
        )

        new_hotkeys = {c.hotkey for c in commits} - self._seen_v6_hotkeys
        if any(c.uid is None for c in commits) or new_hotkeys:
            self._neurons = await _neuron_index(self._subtensor, netuid)
            commits = await scan_v6_active_fast(
                self._subtensor, netuid, self._neurons, snapshot=snapshot
            )

        async with AsyncSessionLocal() as session:
            stats = await self.state_builder.process_commits(session, commits, snapshot=None)
            db_rows = (
                await session.execute(
                    select(MinerCommitment.hotkey).where(
                        MinerCommitment.subnet == netuid,
                        MinerCommitment.version.in_(("v5", "v6")),
                    )
                )
            ).scalars().all()
            await session.commit()

        self._seen_v6_hotkeys = {c.hotkey for c in commits}
        await self._sync_miners_from_cache(netuid, commits)

        db_hotkeys = set(db_rows)
        onchain_hotkeys = {c.hotkey for c in commits}
        stats["needs_full"] = int(onchain_hotkeys != db_hotkeys)

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if stats["new"] > 0:
            logger.warning(
                "NEW v6 commit(s) netuid=%d count=%d uids=%s",
                netuid,
                stats["new"],
                sorted({c.uid for c in commits if c.uid is not None}),
            )
        logger.info(
            "FAST netuid=%d v6=%d new=%d updated=%d unchanged=%d db=%d %dms needs_full=%s",
            netuid,
            len(commits),
            stats["new"],
            stats["updated"],
            stats["unchanged"],
            len(db_hotkeys),
            elapsed_ms,
            bool(stats.get("needs_full")),
        )
        return stats

    async def _encrypted_poll(self, netuid: int, snapshot: ChainSnapshot) -> dict[str, int]:
        commits = scan_encrypted_from_map(netuid, snapshot.commitment_of, self._neurons)

        if any(c.uid is None for c in commits):
            assert self._subtensor is not None
            self._neurons = await _neuron_index(self._subtensor, netuid)
            commits = scan_encrypted_from_map(netuid, snapshot.commitment_of, self._neurons)

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

    async def _full_poll(self, netuid: int, snapshot: ChainSnapshot) -> dict[str, int]:
        assert self._subtensor is not None
        t0 = time.monotonic()
        self._neurons = await _neuron_index(self._subtensor, netuid)
        self._last_metagraph_sync = time.monotonic()

        commits = await scan_v6_from_snapshot(
            snapshot,
            self._neurons,
            self._subtensor,
            include_revealed=True,
            fetch_block_hashes=True,
        )
        snapshot_meta = await self.subtensor_client.get_subnet_snapshot(netuid)
        timelock = timelock_hotkeys_from_map(snapshot.commitment_of)
        present_hotkeys = {c.hotkey for c in commits}

        async with AsyncSessionLocal() as session:
            stats = await self.state_builder.process_commits(session, commits, snapshot_meta)
            pruned = await self.state_builder.prune_absent_v6(
                session,
                netuid,
                present_hotkeys,
                retain_hotkeys=timelock,
            )
            await session.commit()

        self._seen_v6_hotkeys = present_hotkeys
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "FULL netuid=%d v6=%d new=%d updated=%d unchanged=%d pruned=%d %dms uids=%s",
            netuid,
            len(commits),
            stats["new"],
            stats["updated"],
            stats.get("unchanged", 0),
            pruned,
            elapsed_ms,
            sorted({c.uid for c in commits if c.uid is not None}),
        )
        self._last_full_scan = time.monotonic()
        return stats

    async def poll_once(self, netuid: int | None = None) -> dict[str, int]:
        netuid = netuid or self.settings.default_subnet
        assert self._subtensor is not None

        async with self._poll_lock:
            now = time.monotonic()

            if now - self._last_metagraph_sync >= self.settings.metagraph_sync_interval_seconds:
                self._neurons = await _neuron_index(self._subtensor, netuid)
                self._last_metagraph_sync = now

            run_full = now - self._last_full_scan >= self.settings.full_scan_interval_seconds
            run_slot = now - self._last_slot_scan >= self.settings.slot_scan_interval_seconds

            snapshot = await load_chain_snapshot(
                self._subtensor, netuid, include_revealed=True
            )

            if run_full:
                stats = await self._full_poll(netuid, snapshot)
            else:
                stats = await self._fast_poll(netuid, snapshot)
                if stats.get("needs_full"):
                    logger.warning("fast/db hotkey mismatch — running full scan")
                    stats = await self._full_poll(netuid, snapshot)

            await self._encrypted_poll(netuid, snapshot)

            if run_slot:
                await self._slot_poll(netuid, snapshot)
                self._last_slot_scan = now

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
