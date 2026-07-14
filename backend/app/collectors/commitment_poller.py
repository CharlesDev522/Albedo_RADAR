"""Continuous v6 commitment poller — single chain snapshot per cycle."""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from datetime import datetime, timezone

from bittensor.core.async_subtensor import AsyncSubtensor

from app.chain_reader.chain_snapshot import ChainSnapshot, load_chain_snapshot
from app.chain_reader.commitment_scanner import (
    _neuron_index,
    scan_v6_active_fast,
    scan_v6_from_snapshot,
    timelock_hotkeys_from_map,
)
from app.chain_reader.subnet_commit_rules import model_versions_sql_tuple
from app.chain_reader.encrypted_commitment_scanner import scan_encrypted_from_map
from app.chain_reader.slot_commitment_scanner import scan_slots_from_snapshot
from app.collectors.event_publisher import EventPublisher
from app.collectors.subtensor_client import SubtensorClient
from app.config import get_settings
from app.db.init_db import init_db
from app.db.models import Miner, MinerCommitment, MinerStatus
from app.db.session import AsyncSessionLocal, engine
from app.notifications.dispatcher import NotificationDispatcher
from app.notifications.config_log import log_notification_config
from app.notifications.startup_gates import hub_probe_gate_satisfied, startup_ready_for_live
from app.notifications.status import (
    NOTIFICATION_STARTUP_VERSION,
    build_notification_status,
    publish_notification_status,
)
from app.notifications.watcher import NotificationWatcher
from app.processing.commitment_state_builder import CommitmentStateBuilder
from app.processing.encrypted_commitment_state_builder import EncryptedCommitmentStateBuilder
from app.processing.github_repo_watcher import GithubRepoWatcher
from app.processing.incentive_sync import sync_metagraph_incentives
from app.processing.repo_track_builder import RepoTrackBuilder
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
        self.notifier = NotificationDispatcher(self.settings)
        self.notification_watcher = NotificationWatcher(
            dispatcher=self.notifier,
            settings=self.settings,
        )
        self.state_builder = CommitmentStateBuilder(
            publisher=self.publisher,
            notifier=self.notifier,
        )
        self.encrypted_state_builder = EncryptedCommitmentStateBuilder()
        self.slot_status_builder = SlotStatusBuilder(notifier=self.notifier)
        self.repo_track_builder = RepoTrackBuilder(
            settings=self.settings,
            notifier=self.notifier,
        )
        self.github_watcher = GithubRepoWatcher(self.settings)
        self._running = False
        self._neurons: dict[int, dict[str, dict]] = {}
        self._last_full_scan: dict[int, float] = {}
        self._last_slot_scan: dict[int, float] = {}
        self._last_metagraph_sync: dict[int, float] = {}
        self._last_incentive_sync: dict[int, float] = {}
        self._last_repo_track: dict[int, float] = {}
        self._last_github_sync: float = 0.0
        self._notif_task: asyncio.Task[None] | None = None
        self._poll_lock = asyncio.Lock()
        self._seen_hotkeys: dict[int, set[str]] = {}
        self._startup_full_scan_done: set[int] = set()
        self._startup_hub_probes: dict[int, int] = {}
        self._last_hub_probe: dict[int, float] = {}
        self._last_startup_wait_log: float = 0.0
        self._last_status_publish: float = 0.0
        self._collector_started_at: datetime = datetime.now(timezone.utc)

    async def setup(self) -> None:
        await init_db(engine)
        await self.subtensor_client.connect()
        self._subtensor = self.subtensor_client._subtensor
        await self.publisher.connect()
        log_notification_config(self.settings, live=False)
        logger.info(
            "notifications: startup %s grace=%ds hub_probes=%d startup_max=%ds",
            NOTIFICATION_STARTUP_VERSION,
            self.settings.notification_grace_seconds,
            self.settings.notification_min_hub_index_probes,
            self.settings.notification_startup_max_seconds,
        )
        self._collector_started_at = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            loaded = await self.notifier.hydrate(session)
            await self.notification_watcher.bootstrap(session)
            if self.settings.notification_skip_startup_grace:
                self.notifier.enable_resume_mode()
                logger.info(
                    "notifications skip-startup-grace — live immediately (%d prior alerts hydrated)",
                    loaded,
                )
            else:
                live_at = self.notifier.begin_startup_grace(
                    self.settings.notification_grace_seconds
                )
                if loaded > 0:
                    logger.info(
                        "notifications grace period until %s (%ds) — %d prior alerts "
                        "hydrated; initial fetch will NOT post to Slack",
                        live_at.isoformat(),
                        self.settings.notification_grace_seconds,
                        loaded,
                    )
                else:
                    logger.info(
                        "notifications grace period until %s (%ds) — initial fetch will NOT post to Slack",
                        live_at.isoformat(),
                        self.settings.notification_grace_seconds,
                    )
        logger.info("notification cache hydrated (%d source keys)", loaded)
        for netuid in self.settings.dashboard_subnets:
            assert self._subtensor is not None
            self._neurons[netuid] = await _neuron_index(self._subtensor, netuid)
            self._seen_hotkeys.setdefault(netuid, set())
            logger.info(
                "Commitment poller ready — netuid=%d fast=%ds slot=%ds metagraph=%ds full=%ds neurons=%d",
                netuid,
                self.settings.poll_interval_seconds,
                self.settings.slot_scan_interval_seconds,
                self.settings.metagraph_sync_interval_seconds,
                self.settings.full_scan_interval_seconds,
                len(self._neurons[netuid]),
            )
            try:
                await self.poll_once(netuid)
            except Exception:
                logger.exception("Initial poll failed netuid=%d", netuid)
            if (
                not self.notifier.is_live
                and self.settings.notification_min_hub_index_probes > 0
            ):
                try:
                    await self._hub_index_probe(netuid)
                    self._last_hub_probe[netuid] = time.monotonic()
                except Exception:
                    logger.exception("Initial hub index probe failed netuid=%d", netuid)
            try:
                await self._incentive_sync(netuid)
                self._last_incentive_sync[netuid] = time.monotonic()
            except Exception:
                logger.exception("Initial incentive sync failed netuid=%d", netuid)
            try:
                await self._repo_track_poll(netuid)
                self._last_repo_track[netuid] = time.monotonic()
            except Exception:
                logger.exception("Initial repo track failed netuid=%d", netuid)

        await self._maybe_finalize_notifications()
        await self._publish_notification_status(force_log=True)

    def _startup_ready_for_live(self) -> bool:
        return startup_ready_for_live(
            settings=self.settings,
            grace_elapsed=self.notifier.grace_elapsed(),
            is_live=self.notifier.is_live,
            hub_probes_by_subnet=self._startup_hub_probes,
            collector_started_at=self._collector_started_at,
        )

    def _startup_blockers(self) -> list[str]:
        if self.notifier.is_live:
            return []
        blockers: list[str] = []
        if not self.notifier.grace_elapsed():
            remaining = int(
                (self.notifier.live_after - datetime.now(timezone.utc)).total_seconds()
            )
            blockers.append(f"grace {max(remaining, 0)}s remaining")
        required_probes = self.settings.notification_min_hub_index_probes
        max_wait = self.settings.notification_startup_max_seconds
        age = int((datetime.now(timezone.utc) - self._collector_started_at).total_seconds())
        for netuid in self.settings.dashboard_subnets:
            if netuid not in self._startup_full_scan_done:
                blockers.append(f"SN{netuid} full chain scan pending (not required for LIVE)")
            if required_probes <= 0:
                continue
            probes = self._startup_hub_probes.get(netuid, 0)
            if probes < required_probes and not hub_probe_gate_satisfied(
                settings=self.settings,
                probes=probes,
                collector_started_at=self._collector_started_at,
            ):
                need = required_probes - probes
                blockers.append(
                    f"SN{netuid} hub probe {probes}/{required_probes} (HTTP, no DB)"
                )
                if max_wait > 0:
                    blockers.append(f"SN{netuid} fallback LIVE in {max(max_wait - age, 0)}s")
        return blockers

    async def _publish_notification_status(self, *, force_log: bool = False) -> None:
        blockers = [] if self.notifier.is_live else self._startup_blockers()
        payload = build_notification_status(
            settings=self.settings,
            is_live=self.notifier.is_live,
            grace_elapsed=self.notifier.grace_elapsed(),
            live_after=self.notifier.live_after,
            collector_started_at=self._collector_started_at,
            hub_probes=dict(self._startup_hub_probes),
            blockers=blockers,
            seen_keys=self.notifier.seen_key_count,
        )
        await publish_notification_status(self.publisher._redis, payload)
        now = time.monotonic()
        if force_log or self.notifier.is_live or now - self._last_status_publish >= 60:
            self._last_status_publish = now
            logger.info(
                "NOTIFY_STATUS live=%s grace_elapsed=%s uptime=%ss hub_probes=%s blockers=%s",
                payload["is_live"],
                payload["grace_elapsed"],
                payload["collector_uptime_seconds"],
                payload["hub_probes"],
                blockers or "(none)",
            )

    def _log_startup_wait(self) -> None:
        blockers = self._startup_blockers()
        if not blockers:
            return
        now = time.monotonic()
        if now - self._last_startup_wait_log < 30:
            return
        self._last_startup_wait_log = now
        logger.info(
            "notifications not live yet — %s (live after: %s)",
            "; ".join(blockers),
            self.notifier.live_after.isoformat(),
        )

    async def _maybe_finalize_notifications(self) -> None:
        if self.notifier.is_live:
            await self._publish_notification_status()
            return
        required_probes = self.settings.notification_min_hub_index_probes
        if required_probes > 0:
            for netuid in self.settings.dashboard_subnets:
                probes = self._startup_hub_probes.get(netuid, 0)
                if probes < required_probes and self.notifier.grace_elapsed():
                    try:
                        await self._hub_index_probe(netuid)
                    except Exception:
                        logger.exception("Hub index probe before LIVE failed netuid=%d", netuid)
        if not self._startup_ready_for_live():
            self._log_startup_wait()
            await self._publish_notification_status()
            return
        for netuid in self.settings.dashboard_subnets:
            probes = self._startup_hub_probes.get(netuid, 0)
            if required_probes > 0 and probes < required_probes:
                age = int(
                    (datetime.now(timezone.utc) - self._collector_started_at).total_seconds()
                )
                logger.warning(
                    "notifications LIVE without hub probes — SN%d has %d/%d HTTP probes "
                    "after %ds (startup max %ds)",
                    netuid,
                    probes,
                    required_probes,
                    age,
                    self.settings.notification_startup_max_seconds,
                )
        marked = 0
        try:
            async with AsyncSessionLocal() as session:
                marked = await self.notification_watcher.finalize_startup_seed(session)
                await session.commit()
        except Exception:
            logger.warning(
                "notification finalize DB session failed — using HTTP-only seed",
                exc_info=True,
            )
            marked = await self.notification_watcher.finalize_startup_seed_http_only()
        self.notifier.mark_startup_finalized()
        logger.info(
            "notifications LIVE from %s — only changes after docker startup are sent (%d keys seeded)",
            datetime.now(timezone.utc).isoformat(),
            marked,
        )
        log_notification_config(self.settings, live=True)
        await self._publish_notification_status(force_log=True)

    async def _slot_poll(self, netuid: int, snapshot: ChainSnapshot) -> dict[str, int]:
        assert self._subtensor is not None
        neurons = self._neurons.get(netuid, {})
        slots = scan_slots_from_snapshot(snapshot, neurons)
        active_uids = {int(info["uid"]) for info in neurons.values()}
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
        if stats["updated"] > 0:
            try:
                await self._repo_track_poll(netuid)
                self._last_repo_track[netuid] = time.monotonic()
            except Exception:
                logger.exception("Repo track poll after slot update failed netuid=%d", netuid)
        return stats

    async def _notification_loop(self) -> None:
        """Fast duel/crown poll every ~1s; reg fee on a slower cadence."""
        interval = max(self.settings.albedo_notification_poll_seconds, 1)
        reg_every = max(self.settings.notification_reg_fee_poll_seconds, 5)
        last_reg_fee = 0.0
        while self._running:
            now = time.monotonic()
            include_reg_fee = (now - last_reg_fee) >= reg_every
            for netuid in self.settings.dashboard_subnets:
                try:
                    async with AsyncSessionLocal() as session:
                        sent = await self.notification_watcher.poll_subnet(
                            session,
                            netuid,
                            include_reg_fee=include_reg_fee,
                        )
                        await session.commit()
                    if sent:
                        logger.info("NOTIFICATIONS netuid=%d sent=%d", netuid, sent)
                except Exception:
                    logger.exception("Notification poll failed netuid=%d", netuid)
            if include_reg_fee:
                last_reg_fee = now
            await asyncio.sleep(interval)

    async def teardown(self) -> None:
        if self._notif_task is not None:
            self._notif_task.cancel()
            try:
                await self._notif_task
            except asyncio.CancelledError:
                pass
            self._notif_task = None
        await self.notification_watcher.close()
        await self.notifier.close()
        await self.subtensor_client.disconnect()
        await self.publisher.disconnect()
        await self.github_watcher.close()
        await engine.dispose()

    async def _github_poll(self) -> dict[str, int]:
        if not self.github_watcher.enabled:
            return {"targets": 0}
        async with AsyncSessionLocal() as session:
            stats = await self.github_watcher.sync_once(session)
            await session.commit()
        if stats.get("new_commits") or stats.get("seeded") or stats.get("errors"):
            logger.info(
                "GITHUB targets=%d new=%d seeded=%d slack=%d errors=%d",
                stats.get("targets", 0),
                stats.get("new_commits", 0),
                stats.get("seeded", 0),
                stats.get("slack_sent", 0),
                stats.get("errors", 0),
            )
        return stats

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
        neurons = self._neurons.setdefault(netuid, {})
        seen = self._seen_hotkeys.setdefault(netuid, set())
        t0 = time.monotonic()
        commits = await scan_v6_active_fast(
            self._subtensor, netuid, neurons, snapshot=snapshot
        )

        new_hotkeys = {c.hotkey for c in commits} - seen
        if any(c.uid is None for c in commits) or new_hotkeys:
            self._neurons[netuid] = await _neuron_index(self._subtensor, netuid)
            neurons = self._neurons[netuid]
            commits = await scan_v6_active_fast(
                self._subtensor, netuid, neurons, snapshot=snapshot
            )

        async with AsyncSessionLocal() as session:
            stats = await self.state_builder.process_commits(session, commits, snapshot=None)
            db_rows = (
                await session.execute(
                    select(MinerCommitment.hotkey).where(
                        MinerCommitment.subnet == netuid,
                        MinerCommitment.version.in_(model_versions_sql_tuple(netuid)),
                    )
                )
            ).scalars().all()
            await session.commit()

        self._seen_hotkeys[netuid] = {c.hotkey for c in commits}
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
        neurons = self._neurons.setdefault(netuid, {})
        commits = scan_encrypted_from_map(netuid, snapshot.commitment_of, neurons)

        if any(c.uid is None for c in commits):
            assert self._subtensor is not None
            self._neurons[netuid] = await _neuron_index(self._subtensor, netuid)
            neurons = self._neurons[netuid]
            commits = scan_encrypted_from_map(netuid, snapshot.commitment_of, neurons)

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
        self._neurons[netuid] = await _neuron_index(self._subtensor, netuid)
        neurons = self._neurons[netuid]
        self._last_metagraph_sync[netuid] = time.monotonic()

        commits = await scan_v6_from_snapshot(
            snapshot,
            neurons,
            self._subtensor,
            include_revealed=True,
            fetch_block_hashes=True,
        )
        snapshot_meta = await self.subtensor_client.get_subnet_snapshot(netuid)
        timelock = timelock_hotkeys_from_map(snapshot.commitment_of)
        present_hotkeys = {c.hotkey for c in commits}

        async with AsyncSessionLocal() as session:
            stats = await self.state_builder.process_commits(session, commits, snapshot_meta)
            pruned_invalid = await self.state_builder.prune_invalid_subnet_versions(session, netuid)
            pruned_history = await self.state_builder.prune_non_v6_history(session, netuid)
            pruned = await self.state_builder.prune_absent_v6(
                session,
                netuid,
                present_hotkeys,
                retain_hotkeys=timelock,
            )
            await session.commit()

        self._seen_hotkeys[netuid] = present_hotkeys
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "FULL netuid=%d commits=%d new=%d updated=%d unchanged=%d pruned=%d invalid=%d history=%d %dms uids=%s",
            netuid,
            len(commits),
            stats["new"],
            stats["updated"],
            stats.get("unchanged", 0),
            pruned,
            pruned_invalid,
            pruned_history,
            elapsed_ms,
            sorted({c.uid for c in commits if c.uid is not None}),
        )
        self._last_full_scan[netuid] = time.monotonic()
        if not self.notifier.is_live:
            self._startup_full_scan_done.add(netuid)
        return stats

    async def _incentive_sync(self, netuid: int) -> None:
        """Refresh metagraph incentive/emission on active miners (~60s)."""
        assert self._subtensor is not None
        snapshot = await self.subtensor_client.get_subnet_snapshot(netuid)
        async with AsyncSessionLocal() as session:
            await sync_metagraph_incentives(session, snapshot)
            await session.commit()

    async def _hub_index_probe(self, netuid: int) -> None:
        """Lightweight Hippius hub HTTP fetch — counts toward notification startup (no DB)."""
        t0 = time.monotonic()
        count = await self.notification_watcher.probe_hub_index()
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        required = self.settings.notification_min_hub_index_probes
        if not self.notifier.is_live and required > 0:
            self._startup_hub_probes[netuid] = self._startup_hub_probes.get(netuid, 0) + 1
        probes = self._startup_hub_probes.get(netuid, 0)
        logger.info(
            "HUB_PROBE netuid=%d albedo_repos=%d %dms startup_probe=%d/%d",
            netuid,
            count,
            elapsed_ms,
            probes,
            required if required > 0 else 0,
        )

    async def _repo_track_poll(self, netuid: int) -> None:
        t0 = time.monotonic()
        async with AsyncSessionLocal() as session:
            stats = await self.repo_track_builder.sync_subnet(session, netuid)
            await self.repo_track_builder.prune_stale_tracks(session, netuid)
            await session.commit()
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "REPO_TRACK netuid=%d miners=%d repos=%d hub_updates=%d on_chain=%d mismatches=%d errors=%d %dms",
            netuid,
            stats["miners_checked"],
            stats["unique_repos"],
            stats["hub_updates"],
            stats["on_chain_events"],
            stats["mismatches"],
            stats["errors"],
            elapsed_ms,
        )

    async def poll_once(self, netuid: int | None = None) -> dict[str, int]:
        netuid = netuid or self.settings.default_subnet
        assert self._subtensor is not None

        async with self._poll_lock:
            await self._maybe_finalize_notifications()
            now = time.monotonic()

            await self._publish_notification_status()

            if (
                not self.notifier.is_live
                and self.settings.notification_min_hub_index_probes > 0
                and now - self._last_hub_probe.get(netuid, 0.0)
                >= self.settings.repo_track_interval_seconds
            ):
                try:
                    await self._hub_index_probe(netuid)
                except Exception:
                    logger.exception("Hub index probe failed netuid=%d", netuid)
                self._last_hub_probe[netuid] = now

            if now - self._last_repo_track.get(netuid, 0.0) >= self.settings.repo_track_interval_seconds:
                try:
                    await self._repo_track_poll(netuid)
                except Exception:
                    logger.exception("Repo track poll failed netuid=%d", netuid)
                self._last_repo_track[netuid] = now

            if now - self._last_metagraph_sync.get(netuid, 0.0) >= self.settings.metagraph_sync_interval_seconds:
                self._neurons[netuid] = await _neuron_index(self._subtensor, netuid)
                self._last_metagraph_sync[netuid] = now

            if now - self._last_incentive_sync.get(netuid, 0.0) >= self.settings.metagraph_sync_interval_seconds:
                try:
                    await self._incentive_sync(netuid)
                except Exception:
                    logger.exception("Incentive sync failed netuid=%d", netuid)
                self._last_incentive_sync[netuid] = now

            run_full = now - self._last_full_scan.get(netuid, 0.0) >= self.settings.full_scan_interval_seconds
            run_slot = now - self._last_slot_scan.get(netuid, 0.0) >= self.settings.slot_scan_interval_seconds

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
                self._last_slot_scan[netuid] = now

            if (
                self.github_watcher.enabled
                and now - self._last_github_sync >= self.settings.github_poll_interval_seconds
            ):
                try:
                    await self._github_poll()
                except Exception:
                    logger.exception("GitHub repo watch failed")
                self._last_github_sync = now

            return stats

    async def run(self) -> None:
        self._running = True
        await self.setup()
        self._notif_task = asyncio.create_task(
            self._notification_loop(),
            name="albedo-notification-loop",
        )

        while self._running:
            for netuid in self.settings.dashboard_subnets:
                try:
                    await self.poll_once(netuid)
                except Exception:
                    logger.exception("Commitment poll failed netuid=%d", netuid)
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
