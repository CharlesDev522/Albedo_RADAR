"""Single-pass chain storage reads — one CommitmentOf / RevealedCommitments fetch per poll."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.chain_reader.commitment_decoder import decode_revealed_payload, iter_commitment_of_raw


@dataclass
class ChainSnapshot:
    """Cached on-chain commitment data for one subnet poll cycle."""

    netuid: int
    commitment_of: dict[str, dict[str, Any]] = field(default_factory=dict)
    revealed: list[tuple[str, int, str]] | None = None


def _decode_commitment_pair(pair: tuple[Any, Any]) -> tuple[str, list[tuple[int, str]]]:
    key, data = pair
    if not isinstance(key, str):
        key = str(getattr(key, "value", key))
    entries = getattr(data, "value", data)
    out: list[tuple[int, str]] = []
    for entry in entries:
        text, block = entry
        if not isinstance(text, str):
            text = str(text)
        payload = decode_revealed_payload(text)
        if payload:
            out.append((int(block), payload))
    return key, out


async def iter_revealed(subtensor: Any, netuid: int) -> list[tuple[str, int, str]]:
    """Read Commitments.RevealedCommitments with robust decoding."""
    results: list[tuple[str, int, str]] = []
    query = await subtensor.query_map(
        module="Commitments",
        name="RevealedCommitments",
        params=[netuid],
    )
    async for pair in query:
        try:
            hotkey, entries = _decode_commitment_pair(pair)
        except Exception:
            continue
        for block, payload in entries:
            results.append((hotkey, block, payload))
    return results


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
    include_revealed: bool = True,
) -> ChainSnapshot:
    """Load CommitmentOf; merge RevealedCommitments by default for accurate commits."""
    commitment_of = await load_commitment_of(subtensor, netuid)
    revealed = await iter_revealed(subtensor, netuid) if include_revealed else None
    return ChainSnapshot(netuid=netuid, commitment_of=commitment_of, revealed=revealed)
