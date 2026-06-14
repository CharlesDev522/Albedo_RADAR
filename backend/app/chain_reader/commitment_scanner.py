"""Bittensor chain reading — discover v5 model commits on a subnet.

A v5 commitment is a pipe-delimited reveal string: ``v5|<repo>|<sha256:digest>``.
Only v5 commits are tracked; older commitment formats are ignored.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Iterator

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
    """Return (hotkey_ss58, [(block, payload), ...]) for one RevealedCommitments row.

    Handles both hex-serialized SCALE bytes (``0x...``) and raw latin-1 wrapped bytes.
    """
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
            logger.debug("failed to decode commitment for pair", exc_info=True)
            continue
        for block, payload in entries:
            results.append((hotkey, block, payload))
    return results


def _latest_v5_per_hotkey(entries: list[tuple[str, int, str]]) -> dict[str, tuple[int, str]]:
    """Return the highest-block v5 reveal per hotkey."""
    latest: dict[str, tuple[int, str]] = {}
    for hotkey, block, data in entries:
        if parse_v5(data, hotkey) is None:
            continue
        prev = latest.get(hotkey)
        if prev is None or block > prev[0]:
            latest[hotkey] = (block, data)
    return latest


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

        block_at_reg: list[int] = []
        if hasattr(metagraph, "block_at_registration"):
            block_at_reg = [int(b) for b in metagraph.block_at_registration]

        index: dict[str, dict[str, Any]] = {}
        n = int(metagraph.n.item())
        for i in range(n):
            uid = int(metagraph.uids[i].item())
            hotkey = str(metagraph.hotkeys[i])
            coldkey = str(metagraph.coldkeys[i])
            reg_block = block_at_reg[i] if i < len(block_at_reg) else None
            index[hotkey] = {"uid": uid, "coldkey": coldkey, "registered_at_block": reg_block}
        return index
    except Exception:
        logger.warning("metagraph(%d) failed", netuid, exc_info=True)
        return {}


async def scan_v5_commitments(subtensor: Any, netuid: int) -> list[Commit]:
    """Read revealed commitments on ``netuid`` and return latest v5 Commit per hotkey."""
    revealed = await _iter_revealed(subtensor, netuid)
    latest_v5 = _latest_v5_per_hotkey(revealed)
    neurons = await _neuron_index(subtensor, netuid)

    commits: list[Commit] = []
    n_total = len(revealed)
    n_skipped = 0

    for hotkey, (block, data) in latest_v5.items():
        parsed = parse_v5(data, hotkey)
        if parsed is None:
            n_skipped += 1
            continue

        neuron = neurons.get(hotkey)
        uid = neuron["uid"] if neuron else None
        coldkey = neuron["coldkey"] if neuron else None
        reg_block = neuron["registered_at_block"] if neuron else None

        if uid is None:
            logger.warning("no uid for hotkey=%s; including commit without uid", hotkey)

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
            )
        )

    logger.info(
        "scan netuid=%d: revealed_entries=%d hotkeys_with_v5=%d commits=%d skipped=%d",
        netuid,
        n_total,
        len(latest_v5),
        len(commits),
        n_skipped,
    )
    return commits
