"""Single-pass chain storage reads — one CommitmentOf / RevealedCommitments fetch per poll."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.chain_reader.commitment_decoder import iter_commitment_of_raw
from app.chain_reader.commitment_scanner import _iter_revealed


@dataclass
class ChainSnapshot:
    """Cached on-chain commitment data for one subnet poll cycle."""

    netuid: int
    commitment_of: dict[str, dict[str, Any]] = field(default_factory=dict)
    revealed: list[tuple[str, int, str]] | None = None


async def load_commitment_of(subtensor: Any, netuid: int) -> dict[str, dict[str, Any]]:
    """Read all CommitmentOf rows once."""
    rows: dict[str, dict[str, Any]] = {}
    async for hotkey, raw in iter_commitment_of_raw(subtensor, netuid):
        rows[str(hotkey)] = raw
    return rows


async def load_chain_snapshot(
    subtensor: Any,
    netuid: int,
    *,
    include_revealed: bool = False,
) -> ChainSnapshot:
    """Load CommitmentOf; optionally RevealedCommitments in the same cycle."""
    commitment_of = await load_commitment_of(subtensor, netuid)
    revealed = await _iter_revealed(subtensor, netuid) if include_revealed else None
    return ChainSnapshot(netuid=netuid, commitment_of=commitment_of, revealed=revealed)
