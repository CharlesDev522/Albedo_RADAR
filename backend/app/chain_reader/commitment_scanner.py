"""Bittensor chain reading — discover v6 model commits on a subnet."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from app.chain_reader.commitment_decoder import (
    CommitmentKind,
    decode_commitment_of_raw,
    decode_revealed_payload,
)
from app.chain_reader.chain_snapshot import ChainSnapshot

logger = logging.getLogger(__name__)

_BLOCK_HASH_CACHE: OrderedDict[int, str] = OrderedDict()
_BLOCK_HASH_CACHE_MAX = 10_000

MODEL_COMMIT_VERSIONS = frozenset({"v5", "v6", "quasar"})
_MODEL_COMMIT_RE = re.compile(r"^v[56]\|")


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


def parse_model_commit(data: str, chain_hotkey: str) -> dict[str, Any] | None:
    """Parse a v5 or v6 reveal into a payload dict, or None if not well-formed."""
    if not data or not _MODEL_COMMIT_RE.match(data):
        return None
    parts = data.split("|")
    if len(parts) != 3:
        return None
    version, repo, digest = parts
    if version not in ("v5", "v6"):
        return None
    if "/" not in repo or not digest.startswith("sha256:"):
        return None
    return {
        "version": version,
        "repo": repo,
        "digest": digest,
        "author_hotkey": chain_hotkey,
    }


def parse_quasar_commit(data: str, chain_hotkey: str) -> dict[str, Any] | None:
    """Parse SN24 Quasar JSON commit: {"model": "user/repo", "revision": "git_sha"}."""
    if not data or not data.lstrip().startswith("{"):
        return None
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    repo = obj.get("model") or obj.get("hf_repo") or obj.get("hf_repo_id")
    revision = obj.get("revision") or obj.get("king_revision")
    if not repo or not revision or "/" not in str(repo):
        return None
    rev = str(revision).removeprefix("revision:")
    return {
        "version": "quasar",
        "repo": str(repo),
        "digest": f"revision:{rev}",
        "revision": rev,
        "author_hotkey": chain_hotkey,
    }


def parse_any_model_commit(data: str, chain_hotkey: str) -> dict[str, Any] | None:
    """Parse v5/v6 pipe commits or SN24 Quasar JSON commits."""
    parsed = parse_model_commit(data, chain_hotkey)
    if parsed is not None:
        return parsed
    return parse_quasar_commit(data, chain_hotkey)


def parse_v6(data: str, chain_hotkey: str) -> dict[str, Any] | None:
    """Parse v6 only."""
    parsed = parse_model_commit(data, chain_hotkey)
    if parsed is None or parsed["version"] != "v6":
        return None
    return parsed


def is_model_commit(data: str) -> bool:
    return parse_any_model_commit(data, "x") is not None


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def timelock_hotkeys_from_map(commitment_of: dict[str, dict[str, Any]]) -> set[str]:
    """Hotkeys with active TimelockEncrypted on CommitmentOf."""
    blocked: set[str] = set()
    for hotkey, raw in commitment_of.items():
        decoded = decode_commitment_of_raw(raw)
        if decoded.kind == CommitmentKind.TIMELOCK_ENCRYPTED:
            blocked.add(hotkey)
    return blocked


def active_model_from_map(
    commitment_of: dict[str, dict[str, Any]],
) -> dict[str, tuple[int, str]]:
    """Active plaintext v5/v6 per hotkey: (on-chain commit_block, reveal_string)."""
    active: dict[str, tuple[int, str]] = {}
    for hotkey, raw in commitment_of.items():
        decoded = decode_commitment_of_raw(raw)
        if decoded.kind != CommitmentKind.PLAINTEXT or not decoded.reveal_string:
            continue
        parsed = parse_any_model_commit(decoded.reveal_string, hotkey)
        if parsed is None:
            continue
        block = decoded.commit_block or 0
        active[hotkey] = (block, decoded.reveal_string)
    return active


# Backwards-compatible alias
active_v6_from_map = active_model_from_map


async def _iter_revealed(subtensor: Any, netuid: int) -> list[tuple[str, int, str]]:
    from app.chain_reader.chain_snapshot import iter_revealed

    return await iter_revealed(subtensor, netuid)


def _latest_model_commits_per_hotkey(
    entries: list[tuple[str, int, str]],
) -> dict[str, tuple[int, str]]:
    latest: dict[str, tuple[int, str]] = {}
    for hotkey, block, data in entries:
        if parse_any_model_commit(data, hotkey) is None:
            continue
        prev = latest.get(hotkey)
        if prev is None or block > prev[0]:
            latest[hotkey] = (block, data)
    return latest


def _merge_model_commit_sources(
    active: dict[str, tuple[int, str]],
    revealed: dict[str, tuple[int, str]],
    timelock_hotkeys: set[str],
) -> dict[str, tuple[int, str, str]]:
    """Merge active + revealed model commits.

    Active CommitmentOf is authoritative for the current commitment — revealed
    history only fills gaps or refines the block number for the same payload.
    """
    merged: dict[str, tuple[int, str, str]] = {}

    for hotkey, (block, text) in active.items():
        if hotkey in timelock_hotkeys:
            continue
        merged[hotkey] = (block, text, "active")

    for hotkey, (block, data) in revealed.items():
        if hotkey in timelock_hotkeys:
            continue
        if hotkey not in merged:
            merged[hotkey] = (block, data, "revealed")
            continue
        existing_block, existing_data, _ = merged[hotkey]
        if data == existing_data and block >= existing_block:
            merged[hotkey] = (block, data, "revealed")

    return merged


async def _block_hash(subtensor: Any, block: int) -> str | None:
    if block in _BLOCK_HASH_CACHE:
        _BLOCK_HASH_CACHE.move_to_end(block)
        return _BLOCK_HASH_CACHE[block]
    try:
        bh = str(await subtensor.get_block_hash(block))
        _BLOCK_HASH_CACHE[block] = bh
        _BLOCK_HASH_CACHE.move_to_end(block)
        while len(_BLOCK_HASH_CACHE) > _BLOCK_HASH_CACHE_MAX:
            _BLOCK_HASH_CACHE.popitem(last=False)
        return bh
    except Exception:
        logger.debug("get_block_hash(%d) failed", block, exc_info=True)
        return None


async def _block_hashes_batch(subtensor: Any, blocks: set[int]) -> dict[int, str | None]:
    unique = sorted(b for b in blocks if b > 0)
    if not unique:
        return {}
    results = await asyncio.gather(*[_block_hash(subtensor, b) for b in unique])
    return dict(zip(unique, results))


async def _neuron_index(subtensor: Any, netuid: int) -> dict[str, dict[str, Any]]:
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


def _commits_from_merged(
    netuid: int,
    merged: dict[str, tuple[int, str, str]],
    neurons: dict[str, dict[str, Any]],
    block_hashes: dict[int, str | None],
) -> list[Commit]:
    commits: list[Commit] = []
    for hotkey, (block, data, source) in merged.items():
        parsed = parse_any_model_commit(data, hotkey)
        if parsed is None:
            continue
        neuron = neurons.get(hotkey)
        uid = neuron["uid"] if neuron else None
        coldkey = neuron["coldkey"] if neuron else None
        reg_block = neuron["registered_at_block"] if neuron else None
        if uid is None:
            logger.warning("v6 commit for unregistered/unknown hotkey=%s", hotkey)
        commits.append(
            Commit(
                netuid=netuid,
                block_number=block,
                block_hash=block_hashes.get(block),
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
    return commits


async def scan_v6_from_snapshot(
    snapshot: ChainSnapshot,
    neurons: dict[str, dict[str, Any]],
    subtensor: Any | None = None,
    *,
    include_revealed: bool = True,
    fetch_block_hashes: bool = False,
) -> list[Commit]:
    """Build v6 commit list from a pre-loaded chain snapshot."""
    timelock = timelock_hotkeys_from_map(snapshot.commitment_of)
    active = active_model_from_map(snapshot.commitment_of)

    revealed_model: dict[str, tuple[int, str]] = {}
    if include_revealed and snapshot.revealed is not None:
        revealed_model = _latest_model_commits_per_hotkey(snapshot.revealed)

    merged = _merge_model_commit_sources(active, revealed_model, timelock)

    block_hashes: dict[int, str | None] = {}
    if fetch_block_hashes and subtensor is not None and merged:
        blocks = {block for block, _, _ in merged.values()}
        block_hashes = await _block_hashes_batch(subtensor, blocks)

    commits = _commits_from_merged(snapshot.netuid, merged, neurons, block_hashes)
    logger.info(
        "v6 scan netuid=%d active=%d revealed=%d timelock_blocked=%d commits=%d",
        snapshot.netuid,
        len(active),
        len(revealed_model),
        len(timelock),
        len(commits),
    )
    return commits


async def scan_v6_commitments(
    subtensor: Any,
    netuid: int,
    neurons: dict[str, dict[str, Any]] | None = None,
) -> list[Commit]:
    """Full scan: active + revealed with block hashes."""
    from app.chain_reader.chain_snapshot import load_chain_snapshot

    if neurons is None:
        neurons = await _neuron_index(subtensor, netuid)
    snapshot = await load_chain_snapshot(subtensor, netuid, include_revealed=True)
    return await scan_v6_from_snapshot(
        snapshot, neurons, subtensor, include_revealed=True, fetch_block_hashes=True
    )


async def scan_v6_active_fast(
    subtensor: Any,
    netuid: int,
    neurons: dict[str, dict[str, Any]],
    snapshot: ChainSnapshot | None = None,
) -> list[Commit]:
    """Fast path: active + revealed merge every cycle (no block-hash RPCs)."""
    from app.chain_reader.chain_snapshot import load_chain_snapshot

    if snapshot is None:
        snapshot = await load_chain_snapshot(subtensor, netuid, include_revealed=True)
    elif snapshot.revealed is None:
        from app.chain_reader.chain_snapshot import iter_revealed

        snapshot.revealed = await iter_revealed(subtensor, netuid)
    return await scan_v6_from_snapshot(
        snapshot, neurons, include_revealed=True, fetch_block_hashes=False
    )


# Backwards-compatible aliases
scan_v5_commitments = scan_v6_commitments
scan_v5_active_fast = scan_v6_active_fast
