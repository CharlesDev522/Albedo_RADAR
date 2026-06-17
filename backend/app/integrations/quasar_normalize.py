"""Normalize Quasar dashboard.json into API-friendly structures."""

from __future__ import annotations

from collections import Counter
from typing import Any


def submission_counts(submissions: list[dict[str, Any]] | None) -> dict[str, int]:
    if not submissions:
        return {}
    return dict(Counter(str(s.get("status") or "unknown") for s in submissions))


def normalize_status(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {
            "king": None,
            "consensus_king": None,
            "state_king_uid": None,
            "eval_phase": None,
            "current_eval": None,
            "queue_len": 0,
            "submission_counts": {},
            "policy": None,
        }

    status = raw.get("status") or {}
    king_raw = raw.get("king") or {}
    consensus = raw.get("consensus_king") or {}

    king = None
    if king_raw:
        king = {
            "uid": king_raw.get("uid"),
            "hf_repo": king_raw.get("hf_repo"),
            "king_revision": king_raw.get("king_revision"),
            "reign_number": king_raw.get("reign_number"),
            "crowned_at": king_raw.get("crowned_at"),
            "weights_block": king_raw.get("weights_block"),
        }

    chain_king = None
    if consensus:
        chain_king = {
            "uid": consensus.get("uid"),
            "hf_repo": consensus.get("hf_repo"),
            "revision": consensus.get("revision"),
            "support_fraction": consensus.get("support_fraction"),
            "block": consensus.get("block"),
        }

    eval_phase = {
        "active": bool(status.get("active")),
        "phase": status.get("phase") or status.get("mode"),
        "label": status.get("label"),
        "detail": status.get("detail"),
        "state_king_uid": status.get("state_king_uid") or raw.get("state_king_uid"),
        "chain_king_uid": status.get("chain_king_uid"),
        "winner_uid": status.get("winner_uid"),
        "weight_reveal_pending": bool(
            status.get("weight_reveal_pending")
            or (
                status.get("state_king_uid") is not None
                and status.get("chain_king_uid") is not None
                and status.get("state_king_uid") != status.get("chain_king_uid")
            )
        ),
        "current_block": status.get("current_block"),
    }

    return {
        "king": king,
        "consensus_king": chain_king,
        "state_king_uid": raw.get("state_king_uid") or status.get("state_king_uid"),
        "eval_phase": eval_phase,
        "current_eval": raw.get("current_eval"),
        "queue_len": len(raw.get("queue") or []),
        "submission_counts": submission_counts(raw.get("submissions")),
        "policy": raw.get("policy"),
    }
