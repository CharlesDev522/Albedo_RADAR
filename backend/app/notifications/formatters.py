"""Format alert payloads for commits, slots, and repo events."""

from __future__ import annotations

from typing import Any

from app.chain_reader.commitment_scanner import Commit
from app.chain_reader.slot_commitment_scanner import SlotStatus


def commit_alert_detail(commit: Commit, *, previous_hash: str | None = None) -> dict[str, Any]:
    return {
        "uid": commit.uid,
        "hotkey": commit.hotkey,
        "coldkey": commit.coldkey,
        "repo": commit.commit_payload.get("repo"),
        "digest": commit.commit_payload.get("digest"),
        "model_uri": commit.model_uri,
        "version": commit.commit_payload.get("version"),
        "commit_block": commit.block_number,
        "registered_at_block": commit.registered_at_block,
        "commit_source": commit.commit_source,
        "previous_payload_hash": previous_hash,
    }


def slot_alert_detail(slot: SlotStatus, *, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    detail = {
        "uid": slot.uid,
        "hotkey": slot.hotkey,
        "coldkey": slot.coldkey,
        "commitment_type": slot.commitment_type.value,
        "commit_block": slot.commit_block,
        "detail": slot.detail,
        "registered_at_block": slot.registered_at_block,
        "reveal_round": slot.reveal_round,
    }
    if previous:
        detail["previous"] = previous
    return detail


def repo_alert_detail(
    *,
    repo: str,
    event_type: str,
    uid: int | None = None,
    hotkey: str | None = None,
    coldkey: str | None = None,
    model_family: str | None = None,
    hub_digest: str | None = None,
    previous_digest: str | None = None,
    revision: str | None = None,
    commit_message: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "repo": repo,
        "event_type": event_type,
        "uid": uid,
        "hotkey": hotkey,
        "coldkey": coldkey,
        "model_family": model_family,
        "hub_digest": hub_digest,
        "previous_digest": previous_digest,
        "revision": revision,
        "commit_message": commit_message,
    }
    if meta:
        detail["meta"] = meta
    return {k: v for k, v in detail.items() if v is not None}
