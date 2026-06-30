"""Poll Albedo dashboard and subnet economics for crown / reg-fee alerts."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import AlertNotification
from app.integrations.albedo_dashboard import fetch_dashboard
from app.integrations.market_client import fetch_subnet_economics
from app.notifications.dispatcher import NotificationDispatcher

logger = logging.getLogger(__name__)

_URI_RE = re.compile(r"^([^@]+)@")


def _repo_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    m = _URI_RE.match(uri.strip())
    return m.group(1) if m else None


class NotificationWatcher:
    """Stateful poller for crown transitions and registration burn threshold."""

    def __init__(
        self,
        dispatcher: NotificationDispatcher | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.dispatcher = dispatcher or NotificationDispatcher(self.settings)
        self._last_king_version: int | None = None
        self._last_king_uri: str | None = None
        self._reg_fee_below: bool = False
        self._seen_coronation_keys: set[str] = set()

    async def hydrate_seen_keys(self, session: AsyncSession) -> None:
        result = await session.execute(
            select(AlertNotification.source_key).where(
                AlertNotification.kind.in_(("crown_won", "crown_lost"))
            )
        )
        for key in result.scalars().all():
            self._seen_coronation_keys.add(key)

    async def poll_subnet(self, session: AsyncSession, netuid: int) -> int:
        if not self.dispatcher.enabled:
            return 0
        sent = 0
        sent += await self._poll_albedo_crown(session, netuid)
        sent += await self._poll_reg_fee(session, netuid)
        return sent

    async def _poll_albedo_crown(self, session: AsyncSession, netuid: int) -> int:
        if netuid != self.settings.default_subnet:
            return 0
        try:
            dashboard = await fetch_dashboard(settings=self.settings)
        except Exception:
            logger.warning("crown notification: dashboard fetch failed", exc_info=True)
            return 0

        sent = 0
        reign = dashboard.get("reign") or {}
        members = reign.get("members") or []
        current = members[0] if members else {}
        current_version = current.get("king_version")
        current_uri = current.get("model_uri")

        for run in dashboard.get("eval_runs") or []:
            if not isinstance(run, dict) or not run.get("coronated"):
                continue
            eval_id = run.get("eval_run_id") or run.get("id")
            source_key = f"crown_won:{eval_id or run.get('finished_at')}:{run.get('model_uri')}"
            if source_key in self._seen_coronation_keys:
                continue

            repo = _repo_from_uri(run.get("model_uri"))
            king = run.get("king") or {}
            detail = {
                "eval_run_id": eval_id,
                "repo": repo,
                "namespace": run.get("namespace") or (repo.split("/")[0] if repo else None),
                "model_uri": run.get("model_uri"),
                "uid": run.get("uid") or king.get("uid"),
                "hotkey": run.get("hotkey") or king.get("hotkey"),
                "coldkey": run.get("coldkey") or king.get("coldkey"),
                "king_version": run.get("king_version"),
                "defeated_king_version": run.get("defeated_king_version"),
                "win_margin": run.get("win_margin"),
                "finished_at": run.get("finished_at"),
                "challenger_won": run.get("challenger_won"),
            }
            title = f"Crowned — {repo or run.get('model_uri', 'unknown')}"
            msg = (
                f"New king v{run.get('king_version', '?')}"
                f" defeated v{run.get('defeated_king_version', '?')}"
            )
            if await self.dispatcher.notify(
                session,
                kind="crown_won",
                title=title,
                message=msg,
                source_key=source_key,
                detail=detail,
                subnet=netuid,
            ):
                self._seen_coronation_keys.add(source_key)
                sent += 1

        if (
            self._last_king_version is not None
            and current_version is not None
            and current_version != self._last_king_version
        ):
            source_key = f"crown_lost:v{self._last_king_version}->v{current_version}"
            if source_key not in self._seen_coronation_keys:
                detail = {
                    "previous_king_version": self._last_king_version,
                    "previous_model_uri": self._last_king_uri,
                    "new_king_version": current_version,
                    "new_model_uri": current_uri,
                    "new_repo": _repo_from_uri(current_uri),
                }
                title = f"Crown lost — king v{self._last_king_version}"
                msg = f"Reign ended; current king is v{current_version}"
                if await self.dispatcher.notify(
                    session,
                    kind="crown_lost",
                    title=title,
                    message=msg,
                    source_key=source_key,
                    detail=detail,
                    subnet=netuid,
                ):
                    self._seen_coronation_keys.add(source_key)
                    sent += 1

        if current_version is not None:
            self._last_king_version = int(current_version)
            self._last_king_uri = current_uri

        return sent

    async def _poll_reg_fee(self, session: AsyncSession, netuid: int) -> int:
        threshold = self.settings.notification_reg_fee_threshold_tao
        try:
            econ = await fetch_subnet_economics(netuid, settings=self.settings)
        except Exception:
            logger.warning("reg fee notification: economics fetch failed", exc_info=True)
            return 0

        burn = econ.get("registration_burn_tao")
        if burn is None:
            return 0

        below = float(burn) < threshold
        if not below:
            self._reg_fee_below = False
            return 0

        if self._reg_fee_below:
            return 0

        source_key = f"reg_fee_low:sn{netuid}:{burn:.4f}"
        detail: dict[str, Any] = {
            "registration_burn_tao": round(float(burn), 6),
            "threshold_tao": threshold,
            "alpha_price_tao": econ.get("alpha_price_tao"),
            "chain_block": econ.get("chain_block"),
            "network": self.settings.bittensor_network,
        }
        title = f"Low reg fee SN{netuid} — {burn:.4f} τ"
        msg = f"Registration burn {burn:.4f} τ is below {threshold} τ threshold"
        if await self.dispatcher.notify(
            session,
            kind="reg_fee_low",
            title=title,
            message=msg,
            source_key=source_key,
            detail=detail,
            subnet=netuid,
        ):
            self._reg_fee_below = True
            return 1
        return 0
