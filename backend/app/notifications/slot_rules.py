"""When to emit slot Slack alerts (purchase only — skip block↔block and block→none)."""

from __future__ import annotations

from typing import Any

from app.chain_reader.slot_commitment_scanner import SlotStatus


def _is_empty_slot_block(commit_block: int | None, commitment_type: str | None) -> bool:
    if commit_block is not None:
        return False
    if commitment_type is None:
        return True
    return str(commitment_type).lower() in ("none", "")


def is_slot_purchase(
    previous: dict[str, Any],
    slot: SlotStatus,
) -> bool:
    """True only for none/empty → block (new slot bought on an existing UID row)."""
    prev_block = previous.get("commit_block")
    prev_type = previous.get("commitment_type")
    if not _is_empty_slot_block(prev_block, prev_type):
        return False
    return not _is_empty_slot_block(slot.commit_block, slot.commitment_type.value)


def should_notify_slot_new(slot: SlotStatus) -> bool:
    """First DB row for UID — notify only when a slot block is present (purchase)."""
    return not _is_empty_slot_block(slot.commit_block, slot.commitment_type.value)
