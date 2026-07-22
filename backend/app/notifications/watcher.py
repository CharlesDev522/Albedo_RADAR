"""Poll Albedo dashboard and subnet economics for duel / crown / reg-fee alerts."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chain_reader.albedo_model_family import (
    FAMILY_QWEN36_35B,
    FAMILY_QWEN3_4B,
    infer_albedo_model_family,
)
from app.config import Settings, get_settings
from app.db.models import MinerCommitment, MinerSlotStatus, RepoActivityEvent
from app.integrations.albedo_dashboard import fetch_dashboard, fetch_state
from app.integrations.hippius_hub_client import HippiusHubClient
from app.integrations.market_client import fetch_subnet_economics
from app.services.albedo_crown_archive_service import sync_crowns_from_dashboard
from app.notifications.dispatcher import NotificationDispatcher
from app.notifications.repo_alerts import hub_repo_new_source_key
from app.notifications.messages import (
    _duel_participant_detail,
    build_crown_lost_alert,
    build_crown_won_alert,
    build_duel_new_alert,
    build_eval_dq_alert,
    build_eval_queue_entered_alert,
    build_king_defended_alert,
    build_reg_fee_low_alert,
)
from app.services.albedo_eval_queue_service import _parse_pipeline_buckets, parse_dashboard_fails
from app.notifications.reg_fee_tiers import (
    normalize_reg_fee_thresholds,
    tiers_newly_crossed,
    tiers_to_seed_at_bootstrap,
)

logger = logging.getLogger(__name__)

# Hippius terminal states that should trigger eval_dq Slack alerts.
EVAL_DQ_NOTIFY_STATES = frozenset({"TERMINAL_INVALID", "TERMINAL_INFRA_FAILED"})

_URI_RE = re.compile(r"^([^@]+)@")


def _repo_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    m = _URI_RE.match(uri.strip())
    return m.group(1) if m else None


def _crown_won_source_key(run: dict[str, Any]) -> str:
    eval_id = run.get("eval_run_id") or run.get("id")
    return f"crown_won:{eval_id or run.get('finished_at')}:{run.get('model_uri')}"


def _duel_new_source_key(eval_id: str) -> str:
    return f"duel_new:{eval_id}"


def _king_defended_source_key(eval_id: str) -> str:
    return f"king_defended:{eval_id}"


def _eval_queue_entered_source_key(submission_id: str) -> str:
    return f"eval_queue_entered:{submission_id}"


def _eval_queue_participant_detail(participant, *, bucket: str) -> dict[str, Any]:
    return {
        k: v
        for k, v in {
            "submission_id": participant.submission_id,
            "uid": participant.uid,
            "hotkey": participant.hotkey,
            "repo": participant.repo,
            "model_uri": participant.model_uri,
            "state": participant.state,
            "stage": "hippius_validate",
            "bucket": bucket,
            "updated_at": participant.updated_at,
            "commit_block": participant.commit_block,
        }.items()
        if v is not None
    }


def _seed_eval_queue_validate(dispatcher: NotificationDispatcher, state: dict[str, Any] | None) -> None:
    for bucket_name, participants in _hippius_validate_participants(state):
        for participant in participants:
            if participant.submission_id:
                dispatcher.mark_seen(_eval_queue_entered_source_key(participant.submission_id))


def _hippius_validate_participants(state: dict[str, Any] | None):
    buckets = _parse_pipeline_buckets(state, lookup=None)
    validate = next((b for b in buckets if b.stage == "hippius_validate"), None)
    if not validate:
        return []
    return [("queued", validate.queued), ("running", validate.running)]


def _eval_dq_source_key(
    *,
    submission_id: str | None = None,
    eval_run_id: str | None = None,
    uid: int | None = None,
    hotkey: str | None = None,
    updated_at: str | None = None,
) -> str:
    if submission_id:
        return f"eval_dq:{submission_id}"
    if eval_run_id:
        return f"eval_dq:run:{eval_run_id}"
    return f"eval_dq:{uid or '?'}:{hotkey or '?'}:{updated_at or '?'}"


def _eval_dq_detail(fail) -> dict[str, Any]:
    return {
        k: v
        for k, v in {
            "submission_id": fail.submission_id,
            "eval_run_id": fail.eval_run_id,
            "uid": fail.uid,
            "hotkey": fail.hotkey,
            "repo": fail.repo,
            "model_uri": fail.model_uri,
            "state": fail.state,
            "fault_class": fail.fault_class,
            "fault_code": fail.fault_code,
            "fault_message": fail.fault_message,
            "updated_at": fail.updated_at,
        }.items()
        if v is not None
    }


class NotificationWatcher:
    """Stateful poller for duels, crown transitions, and registration burn threshold."""

    def __init__(
        self,
        dispatcher: NotificationDispatcher | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.dispatcher = dispatcher or NotificationDispatcher(self.settings)
        self._last_king_version: int | None = None
        self._last_king_uri: str | None = None
        self._reg_fee_alerted_tiers: set[float] = set()
        self._bootstrapped: bool = False
        self._last_live_eval_id: str | None = None
        self._http: httpx.AsyncClient | None = None

    def _http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.settings.notification_http_timeout_seconds)
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def bootstrap(self, session: AsyncSession | None = None) -> None:
        """Seed dashboard state so only post-startup changes notify Slack."""
        if self._bootstrapped or not self.dispatcher.enabled:
            return
        netuid = self.settings.default_subnet
        try:
            dashboard = await fetch_dashboard(settings=self.settings)
        except Exception:
            logger.warning("notification bootstrap: dashboard fetch failed", exc_info=True)
            return

        state: dict[str, Any] | None = None
        try:
            state = await fetch_state(settings=self.settings)
        except Exception:
            logger.debug("notification bootstrap: state fetch failed", exc_info=True)

        if session is not None:
            try:
                await sync_crowns_from_dashboard(session, netuid, dashboard)
            except Exception:
                logger.warning("crown archive bootstrap sync failed", exc_info=True)

        for run in dashboard.get("eval_runs") or []:
            if not isinstance(run, dict):
                continue
            eval_id = run.get("eval_run_id") or run.get("id")
            if run.get("coronated"):
                self.dispatcher.mark_seen(_crown_won_source_key(run))
            if (
                eval_id
                and run.get("finished_at")
                and run.get("challenger_won") is False
                and not run.get("coronated")
            ):
                self.dispatcher.mark_seen(_king_defended_source_key(str(eval_id)))

        current_eval = dashboard.get("current_eval") or {}
        if isinstance(current_eval, dict):
            live_id = current_eval.get("eval_run_id")
            if live_id:
                self._last_live_eval_id = str(live_id)
                self.dispatcher.mark_seen(_duel_new_source_key(self._last_live_eval_id))

        for raw in dashboard.get("fails") or []:
            if not isinstance(raw, dict):
                continue
            if raw.get("state") not in EVAL_DQ_NOTIFY_STATES:
                continue
            self.dispatcher.mark_seen(
                _eval_dq_source_key(
                    submission_id=raw.get("submission_id"),
                    eval_run_id=raw.get("eval_run_id"),
                    uid=int(raw["uid"]) if raw.get("uid") is not None else None,
                    hotkey=raw.get("hotkey"),
                    updated_at=raw.get("updated_at"),
                )
            )

        _seed_eval_queue_validate(self.dispatcher, state)

        reign = dashboard.get("reign") or {}
        members = reign.get("members") or []
        current = members[0] if members else {}
        current_version = current.get("king_version")
        if current_version is not None:
            self._last_king_version = int(current_version)
            self._last_king_uri = current.get("model_uri")

        thresholds = self._reg_fee_thresholds()
        try:
            econ = await fetch_subnet_economics(netuid, settings=self.settings)
            burn = econ.get("registration_burn_tao")
            if burn is not None and thresholds:
                self._reg_fee_alerted_tiers |= tiers_to_seed_at_bootstrap(
                    float(burn), thresholds
                )
        except Exception:
            logger.debug("notification bootstrap: reg fee seed skipped", exc_info=True)

        self._bootstrapped = True
        logger.info(
            "notification bootstrap SN%d king=v%s live_duel=%s reg_tiers_alerted=%s",
            netuid,
            self._last_king_version,
            self._last_live_eval_id,
            sorted(self._reg_fee_alerted_tiers, reverse=True),
        )

    async def probe_hub_index(self) -> int:
        """Fetch Hippius hub index over HTTP only (no DB). Returns albedo repo count."""
        hub = HippiusHubClient(self.settings)
        timeout = self.settings.market_http_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            index = await hub.fetch_albedo_index(client=client)
        count = 0
        for repo in index:
            family = infer_albedo_model_family(repo)
            if family in (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B):
                count += 1
        return count

    async def _seed_hub_index_keys(self) -> int:
        """Mark current Hippius hub albedo repos as seen (anti-bulk when repo track sync fails)."""
        marked = 0
        try:
            hub = HippiusHubClient(self.settings)
            timeout = self.settings.market_http_timeout_seconds
            async with httpx.AsyncClient(timeout=timeout) as client:
                index = await hub.fetch_albedo_index(client=client)
        except Exception:
            logger.warning("notification hub index seed failed", exc_info=True)
            return 0

        for repo, entry in index.items():
            family = infer_albedo_model_family(repo)
            if family not in (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B):
                continue
            sk = hub_repo_new_source_key(host="hippius", repo=repo)
            if not self.dispatcher.is_seen(sk):
                self.dispatcher.mark_seen(sk)
                marked += 1
        if marked:
            logger.info("notification hub index seed — marked %d repos from Hippius hub", marked)
        return marked

    async def _seed_known_hf_repos(self, session: AsyncSession | None) -> int:
        """Mark known Hugging Face repos so only post-startup discoveries notify."""
        marked = 0
        repos: set[str] = set()
        if session is not None:
            try:
                from app.db.models import HippiusRepoTrack

                rows = (
                    await session.execute(
                        select(HippiusRepoTrack.repo).where(HippiusRepoTrack.repo_host == "huggingface")
                    )
                ).scalars().all()
                repos.update(rows)
            except Exception:
                logger.debug("notification HF DB seed skipped", exc_info=True)

        try:
            from app.services.huggingface_latest_service import discover_huggingface_repos

            timeout = self.settings.market_http_timeout_seconds
            async with httpx.AsyncClient(timeout=timeout) as client:
                from app.integrations.huggingface_registry import HuggingFaceRegistryClient

                hf = HuggingFaceRegistryClient(self.settings)
                repos.update(await discover_huggingface_repos(hf, client))
        except Exception:
            logger.debug("notification HF discovery seed skipped", exc_info=True)

        for repo in repos:
            sk = hub_repo_new_source_key(host="huggingface", repo=repo)
            if not self.dispatcher.is_seen(sk):
                self.dispatcher.mark_seen(sk)
                marked += 1
        if marked:
            logger.info("notification HF seed — marked %d repos", marked)
        return marked

    async def _seed_db_keys(self, session: AsyncSession) -> int:
        """Best-effort DB seed — failures must not block going LIVE."""
        marked = 0
        try:
            repo_keys = (
                await session.execute(select(RepoActivityEvent.source_key))
            ).scalars().all()
            for key in repo_keys:
                sk = f"alert:{key}"
                if not self.dispatcher.is_seen(sk):
                    self.dispatcher.mark_seen(sk)
                    marked += 1

            for row in (await session.execute(select(MinerCommitment))).scalars().all():
                for prefix in ("commit_new", "commit_updated"):
                    sk = f"{prefix}:{row.subnet}:{row.hotkey}:{row.payload_hash}"
                    if not self.dispatcher.is_seen(sk):
                        self.dispatcher.mark_seen(sk)
                        marked += 1

            for row in (await session.execute(select(MinerSlotStatus))).scalars().all():
                sk_new = f"slot_new:{row.subnet}:{row.uid}:{row.payload_hash or row.commitment_type}"
                sk_chg = f"slot_changed:{row.subnet}:{row.uid}:{row.payload_hash or row.commit_block}"
                for sk in (sk_new, sk_chg):
                    if not self.dispatcher.is_seen(sk):
                        self.dispatcher.mark_seen(sk)
                        marked += 1
        except Exception:
            logger.warning("notification DB seed failed (continuing with HTTP seed)", exc_info=True)
        return marked

    async def finalize_startup_seed(self, session: AsyncSession) -> int:
        """Mark ingested state as seen. DB is best-effort; hub + dashboard use HTTP."""
        marked = await self._seed_db_keys(session)

        self._bootstrapped = False
        try:
            await self.bootstrap(session)
        except Exception:
            logger.warning("notification dashboard bootstrap failed during finalize", exc_info=True)

        marked += await self._seed_hub_index_keys()
        marked += await self._seed_known_hf_repos(session)
        logger.info("notification startup seed complete — marked %d keys", marked)
        return marked

    async def finalize_startup_seed_http_only(self) -> int:
        """Seed without DB when the session is unavailable."""
        marked = 0
        self._bootstrapped = False
        try:
            await self.bootstrap(None)
        except Exception:
            logger.warning("notification dashboard bootstrap failed (HTTP-only)", exc_info=True)
        marked += await self._seed_hub_index_keys()
        marked += await self._seed_known_hf_repos(None)
        logger.info("notification HTTP-only seed complete — marked %d keys", marked)
        return marked

    def _reg_fee_thresholds(self) -> list[float]:
        return normalize_reg_fee_thresholds(self.settings.notification_reg_fee_thresholds_tao)

    async def poll_subnet(
        self, session: AsyncSession, netuid: int, *, include_reg_fee: bool = True
    ) -> int:
        if not self.dispatcher.enabled:
            return 0
        if not self._bootstrapped:
            await self.bootstrap(session)
        sent = 0
        sent += await self._poll_albedo_duels(session, netuid)
        if include_reg_fee:
            sent += await self._poll_reg_fee(session, netuid)
        return sent

    async def _poll_albedo_duels(self, session: AsyncSession, netuid: int) -> int:
        if netuid != self.settings.default_subnet:
            return 0
        try:
            dashboard = await fetch_dashboard(
                settings=self.settings,
                fresh=True,
                client=self._http_client(),
            )
        except Exception:
            logger.warning("duel notification: dashboard fetch failed", exc_info=True)
            return 0

        try:
            await sync_crowns_from_dashboard(session, netuid, dashboard)
        except Exception:
            logger.warning("crown archive sync failed", exc_info=True)

        sent = 0
        crown_won_sent = False
        reign = dashboard.get("reign") or {}
        members = reign.get("members") or []
        reign_king = members[0] if members else {}
        current_version = reign_king.get("king_version")
        current_uri = reign_king.get("model_uri")

        sent += await self._poll_duel_new(session, netuid, dashboard, reign_king)

        for run in dashboard.get("eval_runs") or []:
            if not isinstance(run, dict):
                continue
            eval_id = run.get("eval_run_id") or run.get("id")

            if run.get("coronated"):
                source_key = _crown_won_source_key(run)
                if self.dispatcher.is_seen(source_key):
                    continue
                repo = _repo_from_uri(run.get("model_uri"))
                king = run.get("king") or {}
                detail = _duel_participant_detail(run, repo_from_uri=_repo_from_uri)
                detail.update(
                    {
                        "defeated_king_version": run.get("defeated_king_version"),
                        "challenger_won": run.get("challenger_won"),
                    }
                )
                alert = build_crown_won_alert(
                    netuid=netuid,
                    source_key=source_key,
                    detail=detail,
                    repo=repo,
                    model_uri=run.get("model_uri"),
                    king_version=run.get("king_version"),
                    defeated_king_version=run.get("defeated_king_version"),
                )
                if await self.dispatcher.notify_content(session, alert):
                    sent += 1
                    crown_won_sent = True
                continue

            if (
                eval_id
                and run.get("finished_at")
                and run.get("challenger_won") is False
                and not run.get("coronated")
            ):
                source_key = _king_defended_source_key(str(eval_id))
                if self.dispatcher.is_seen(source_key):
                    continue
                repo = _repo_from_uri(run.get("model_uri"))
                detail = _duel_participant_detail(run, repo_from_uri=_repo_from_uri)
                alert = build_king_defended_alert(
                    netuid=netuid,
                    source_key=source_key,
                    detail=detail,
                    repo=repo,
                )
                if await self.dispatcher.notify_content(session, alert):
                    sent += 1

        if (
            not crown_won_sent
            and self._last_king_version is not None
            and current_version is not None
            and current_version != self._last_king_version
        ):
            source_key = f"crown_lost:v{self._last_king_version}->v{current_version}"
            if not self.dispatcher.is_seen(source_key):
                detail = {
                    "previous_king_version": self._last_king_version,
                    "previous_model_uri": self._last_king_uri,
                    "new_king_version": current_version,
                    "new_model_uri": current_uri,
                    "new_repo": _repo_from_uri(current_uri),
                }
                alert = build_crown_lost_alert(
                    netuid=netuid,
                    source_key=source_key,
                    detail=detail,
                    previous_king_version=self._last_king_version,
                    current_version=current_version,
                )
                if await self.dispatcher.notify_content(session, alert):
                    sent += 1

        if current_version is not None:
            self._last_king_version = int(current_version)
            self._last_king_uri = current_uri

        sent += await self._poll_eval_dq_fails(session, netuid, dashboard)
        sent += await self._poll_eval_queue_validate(session, netuid)

        return sent

    async def _poll_eval_queue_validate(self, session: AsyncSession, netuid: int) -> int:
        if netuid != self.settings.default_subnet:
            return 0
        try:
            state = await fetch_state(
                settings=self.settings,
                fresh=True,
                client=self._http_client(),
            )
        except Exception:
            logger.warning("eval queue notification: state fetch failed", exc_info=True)
            return 0

        participants = list(_hippius_validate_participants(state))
        total = sum(len(p[1]) for p in participants)
        if total and logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "eval queue poll SN%d: %d hippius_validate participants (queued+running)",
                netuid,
                total,
            )

        sent = 0
        for bucket_name, participants in _hippius_validate_participants(state):
            for participant in participants:
                submission_id = participant.submission_id
                if not submission_id:
                    continue
                source_key = _eval_queue_entered_source_key(submission_id)
                if self.dispatcher.is_seen(source_key):
                    continue
                detail = _eval_queue_participant_detail(participant, bucket=bucket_name)
                alert = build_eval_queue_entered_alert(
                    netuid=netuid,
                    source_key=source_key,
                    detail=detail,
                    repo=participant.repo,
                )
                if await self.dispatcher.notify_content(session, alert):
                    sent += 1
        return sent

    async def _poll_eval_dq_fails(
        self,
        session: AsyncSession,
        netuid: int,
        dashboard: dict[str, Any],
    ) -> int:
        if netuid != self.settings.default_subnet:
            return 0
        sent = 0
        for fail in parse_dashboard_fails(dashboard, limit=200):
            if fail.state not in EVAL_DQ_NOTIFY_STATES:
                continue
            source_key = _eval_dq_source_key(
                submission_id=fail.submission_id,
                eval_run_id=fail.eval_run_id,
                uid=fail.uid,
                hotkey=fail.hotkey,
                updated_at=fail.updated_at,
            )
            if self.dispatcher.is_seen(source_key):
                continue
            alert = build_eval_dq_alert(
                netuid=netuid,
                source_key=source_key,
                detail=_eval_dq_detail(fail),
                repo=fail.repo,
            )
            if await self.dispatcher.notify_content(session, alert):
                sent += 1
        return sent

    async def _poll_duel_new(
        self,
        session: AsyncSession,
        netuid: int,
        dashboard: dict[str, Any],
        reign_king: dict[str, Any],
    ) -> int:
        current_eval = dashboard.get("current_eval")
        if not isinstance(current_eval, dict):
            return 0
        eval_id = current_eval.get("eval_run_id")
        if not eval_id:
            return 0
        eval_id = str(eval_id)
        source_key = _duel_new_source_key(eval_id)
        if self.dispatcher.is_seen(source_key):
            self._last_live_eval_id = eval_id
            return 0

        alert = build_duel_new_alert(
            netuid=netuid,
            source_key=source_key,
            current_eval=current_eval,
            repo_from_uri=_repo_from_uri,
            reign_king=reign_king,
        )
        if await self.dispatcher.notify_content(session, alert):
            self._last_live_eval_id = eval_id
            return 1
        return 0

    async def _poll_reg_fee(self, session: AsyncSession, netuid: int) -> int:
        thresholds = self._reg_fee_thresholds()
        if not thresholds:
            return 0
        try:
            econ = await fetch_subnet_economics(netuid, settings=self.settings)
        except Exception:
            logger.warning("reg fee notification: economics fetch failed", exc_info=True)
            return 0

        burn = econ.get("registration_burn_tao")
        if burn is None:
            return 0

        burn_f = float(burn)
        if burn_f >= max(thresholds):
            self._reg_fee_alerted_tiers.clear()
            return 0

        crossed = tiers_newly_crossed(burn_f, thresholds, self._reg_fee_alerted_tiers)
        if not crossed:
            return 0

        sent = 0
        for tier in crossed:
            source_key = f"reg_fee_low:sn{netuid}:tier_{tier:g}"
            detail: dict[str, Any] = {
                "registration_burn_tao": round(burn_f, 6),
                "threshold_tao": tier,
                "alpha_price_tao": econ.get("alpha_price_tao"),
                "chain_block": econ.get("chain_block"),
                "network": self.settings.bittensor_network,
            }
            alert = build_reg_fee_low_alert(
                netuid=netuid,
                source_key=source_key,
                detail=detail,
                burn=burn_f,
                threshold=tier,
            )
            if await self.dispatcher.notify_content(session, alert):
                self._reg_fee_alerted_tiers.add(tier)
                sent += 1
        return sent
