"""Bittensor chain reading — discover v5 model commits on a subnet.

Scans two on-chain sources:
  - ``CommitmentOf`` — current active commitment per hotkey (where new v5 commits appear first)
  - ``RevealedCommitments`` — historical reveal log with block numbers

A v5 commitment is: ``v5|<repo>|<sha256:digest>``
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_BLOCK_HASH_CACHE: dict[int, str] = {}


@dataclass(frozen=True)
class Commit:
    netuid: int
    block_number: int
    block_hash: str | None
    uid: int | None
    hotkey: str
    coldkey: str | None
    registered_at_block: int | None
    commit_payload: dict[str, Any]
    reveal_string: str
    model_uri: str
    payload_hash: str
    commit_source: str  # "active" | "revealed"


def parse_v5(data: str, chain_hotkey: str) -> dict[str, Any] | None:
    """Parse a v5 reveal into a payload dict, or None if not well-formed v5."""
    if not data.startswith("v5|"):
        return None
    parts = data.split("|")
    if len(parts) != 3:
        return None
    _, repo, digest = parts
    if "/" not in repo or not digest.startswith("sha256:"):
        return None
    return {
        "version": "v5",
        "repo": repo,
        "digest": digest,
        "author_hotkey": chain_hotkey,
    }


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _decode_commitment_pair(pair: tuple[Any, Any]) -> tuple[str, list[tuple[int, str]]]:
    """Return (hotkey_ss58, [(block, payload), ...]) for one RevealedCommitments row."""
    key, data = pair
    if not isinstance(key, str):
        key = str(getattr(key, "value", key))
    entries = getattr(data, "value", data)
    out: list[tuple[int, str]] = []
    for entry in entries:
        text, block = entry
        if not isinstance(text, str):
            text = str(text)
        if text.startswith(("0x", "0X")):
            raw = bytes.fromhex(text[2:])
        else:
            raw = text.encode("latin-1")
        if not raw:
            continue
        mode = raw[0] & 0b11
        offset = 1 if mode == 0 else 2 if mode == 1 else 4
        out.append((int(block), raw[offset:].decode("utf-8", errors="ignore")))
    return key, out


async def _iter_revealed(subtensor: Any, netuid: int) -> list[tuple[str, int, str]]:
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
            logger.debug("failed to decode revealed commitment", exc_info=True)
            continue
        for block, payload in entries:
            results.append((hotkey, block, payload))
    return results


async def _iter_active_commitments(subtensor: Any, netuid: int) -> dict[str, str]:
    """Read current CommitmentOf per hotkey via SDK decoder."""
    try:
        return await subtensor.get_all_commitments(netuid)
    except Exception:
        logger.warning("get_all_commitments(%d) failed", netuid, exc_info=True)
        return {}


def _latest_v5_per_hotkey(entries: list[tuple[str, int, str]]) -> dict[str, tuple[int, str]]:
    """Return the highest-block v5 reveal per hotkey from revealed history."""
    latest: dict[str, tuple[int, str]] = {}
    for hotkey, block, data in entries:
        if parse_v5(data, hotkey) is None:
            continue
        prev = latest.get(hotkey)
        if prev is None or block > prev[0]:
            latest[hotkey] = (block, data)
    return latest


def _merge_v5_sources(
    active: dict[str, str],
    revealed: dict[str, tuple[int, str]],
    current_block: int,
) -> dict[str, tuple[int, str, str]]:
    """Merge active CommitmentOf and RevealedCommitments into latest v5 per hotkey."""
    merged: dict[str, tuple[int, str, str]] = {}

    for hotkey, text in active.items():
        if parse_v5(text, hotkey) is not None:
            merged[hotkey] = (current_block, text, "active")

    for hotkey, (block, data) in revealed.items():
        if hotkey in merged:
            existing_block, existing_data, _ = merged[hotkey]
            # Prefer revealed block when payload matches or revealed is newer
            if data == existing_data or block >= existing_block:
                merged[hotkey] = (block, data, "revealed")
        else:
            merged[hotkey] = (block, data, "revealed")

    return merged


async def _block_hash(subtensor: Any, block: int) -> str | None:
    if block in _BLOCK_HASH_CACHE:
        return _BLOCK_HASH_CACHE[block]
    try:
        bh = str(await subtensor.get_block_hash(block))
        _BLOCK_HASH_CACHE[block] = bh
        return bh
    except Exception:
        logger.debug("get_block_hash(%d) failed", block, exc_info=True)
        return None


async def _neuron_index(subtensor: Any, netuid: int) -> dict[str, dict[str, Any]]:
    """Map hotkey -> {uid, coldkey, registered_at_block} from metagraph."""
    from bittensor.core.metagraph import async_metagraph

    try:
        metagraph = await async_metagraph(netuid=netuid, lite=True, subtensor=subtensor)
        await metagraph.sync(subtensor=subtensor)

        reg_blocks: list[int] = list(getattr(metagraph, "block_at_registration", []) or [])

        index: dict[str, dict[str, Any]] = {}
        for i, neuron in enumerate(metagraph.neurons):
            if getattr(neuron, "is_null", False):
                continue
            uid = int(neuron.uid)
            hotkey = str(neuron.hotkey)
            coldkey = str(neuron.coldkey)
            reg_block = int(reg_blocks[i]) if i < len(reg_blocks) else None
            index[hotkey] = {"uid": uid, "coldkey": coldkey, "registered_at_block": reg_block}
        return index
    except Exception:
        logger.warning("metagraph(%d) failed", netuid, exc_info=True)
        return {}


async def scan_v5_commitments(subtensor: Any, netuid: int) -> list[Commit]:
    """Read active + revealed commitments and return latest v5 Commit per hotkey."""
    current_block = await subtensor.get_current_block()
    active = await _iter_active_commitments(subtensor, netuid)
    revealed_entries = await _iter_revealed(subtensor, netuid)
    revealed_v5 = _latest_v5_per_hotkey(revealed_entries)
    merged = _merge_v5_sources(active, revealed_v5, current_block)
    neurons = await _neuron_index(subtensor, netuid)

    commits: list[Commit] = []
    n_active_v5 = sum(1 for t in active.values() if parse_v5(str(t), "x") is not None)

    for hotkey, (block, data, source) in merged.items():
        parsed = parse_v5(data, hotkey)
        if parsed is None:
            continue

        neuron = neurons.get(hotkey)
        uid = neuron["uid"] if neuron else None
        coldkey = neuron["coldkey"] if neuron else None
        reg_block = neuron["registered_at_block"] if neuron else None

        if uid is None:
            logger.warning("v5 commit for unregistered/unknown hotkey=%s", hotkey)

        commits.append(
            Commit(
                netuid=netuid,
                block_number=block,
                block_hash=await _block_hash(subtensor, block),
                uid=uid,
                hotkey=hotkey,
                coldkey=coldkey,
                registered_at_block=reg_block,
                commit_payload=parsed,
                reveal_string=data,
                model_uri=f"{parsed['repo']}@{parsed['digest']}",
                payload_hash=payload_hash(parsed),
                commit_source=source,
            )
        )

    logger.info(
        "scan netuid=%d: active_v5=%d revealed_v5=%d merged=%d commits=%d",
        netuid,
        n_active_v5,
        len(revealed_v5),
        len(merged),
        len(commits),
    )
    return commits


async def scan_v5_active_fast(
    subtensor: Any,
    netuid: int,
    neurons: dict[str, dict[str, Any]],
) -> list[Commit]:
    """Fast path: CommitmentOf only (~1-2s). Used for near-instant new-commit detection."""
    current_block = await subtensor.get_current_block()
    active = await _iter_active_commitments(subtensor, netuid)
    commits: list[Commit] = []

    for hotkey, text in active.items():
        data = str(text)
        parsed = parse_v5(data, hotkey)
        if parsed is None:
            continue
        neuron = neurons.get(hotkey)
        uid = neuron["uid"] if neuron else None
        coldkey = neuron["coldkey"] if neuron else None
        reg_block = neuron["registered_at_block"] if neuron else None
        commits.append(
            Commit(
                netuid=netuid,
                block_number=current_block,
                block_hash=None,
                uid=uid,
                hotkey=hotkey,
                coldkey=coldkey,
                registered_at_block=reg_block,
                commit_payload=parsed,
                reveal_string=data,
                model_uri=f"{parsed['repo']}@{parsed['digest']}",
                payload_hash=payload_hash(parsed),
                commit_source="active",
            )
        )
    return commits
