"""Relationship builder for coldkey-hotkey-UID graph intelligence."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ColdkeyRecord, HotkeyRecord, Miner, MinerStatus

logger = logging.getLogger(__name__)


class RelationshipBuilder:
    """Builds wallet clustering and relationship graph data."""

    async def get_coldkey_graph(self, session: AsyncSession, coldkey: str) -> dict[str, Any]:
        """Return relationship graph for a coldkey."""
        result = await session.execute(select(ColdkeyRecord).where(ColdkeyRecord.coldkey == coldkey))
        record = result.scalar_one_or_none()
        if not record:
            return {"coldkey": coldkey, "nodes": [], "edges": []}

        miners_result = await session.execute(
            select(Miner).where(Miner.coldkey == coldkey, Miner.status == MinerStatus.ACTIVE)
        )
        miners = list(miners_result.scalars().all())

        nodes: list[dict[str, Any]] = [
            {"id": f"coldkey:{coldkey}", "type": "coldkey", "label": coldkey[:12] + "..."}
        ]
        edges: list[dict[str, Any]] = []

        hotkeys_seen: set[str] = set()
        for miner in miners:
            hotkey_id = f"hotkey:{miner.hotkey}"
            uid_id = f"uid:{miner.subnet}:{miner.uid}"

            if miner.hotkey not in hotkeys_seen:
                nodes.append({"id": hotkey_id, "type": "hotkey", "label": miner.hotkey[:12] + "..."})
                edges.append({"source": f"coldkey:{coldkey}", "target": hotkey_id, "type": "owns"})
                hotkeys_seen.add(miner.hotkey)

            nodes.append({
                "id": uid_id,
                "type": "uid",
                "label": f"UID {miner.uid}",
                "subnet": miner.subnet,
                "stake": miner.current_stake,
                "emission": miner.current_emission,
            })
            edges.append({"source": hotkey_id, "target": uid_id, "type": "operates"})

        return {
            "coldkey": coldkey,
            "miner_count": record.miner_count,
            "validator_count": record.validator_count,
            "total_stake": record.total_stake,
            "total_emission": record.total_emission,
            "nodes": nodes,
            "edges": edges,
        }

    async def detect_clusters(self, session: AsyncSession, subnet: int, min_miners: int = 3) -> list[dict[str, Any]]:
        """Detect coldkeys operating multiple miners (potential farms)."""
        result = await session.execute(
            select(ColdkeyRecord).where(ColdkeyRecord.miner_count >= min_miners)
        )
        records = list(result.scalars().all())

        clusters = []
        for record in records:
            if subnet in record.subnets or not record.subnets:
                clusters.append({
                    "coldkey": record.coldkey,
                    "miner_count": record.miner_count,
                    "validator_count": record.validator_count,
                    "total_stake": record.total_stake,
                    "total_emission": record.total_emission,
                    "hotkey_count": len(record.hotkeys),
                    "subnets": record.subnets,
                })

        clusters.sort(key=lambda c: c["miner_count"], reverse=True)
        return clusters

    async def get_hotkey_history(self, session: AsyncSession, hotkey: str) -> list[dict[str, Any]]:
        """Return UID history for a hotkey across subnets."""
        result = await session.execute(select(HotkeyRecord).where(HotkeyRecord.hotkey == hotkey))
        records = list(result.scalars().all())

        history = []
        for record in records:
            history.append({
                "subnet": record.subnet,
                "current_uid": record.uid,
                "is_active": record.is_active,
                "coldkey": record.coldkey,
                "first_seen": record.first_seen.isoformat(),
                "last_seen": record.last_seen.isoformat(),
                "uid_history": record.uid_history,
            })
        return history
