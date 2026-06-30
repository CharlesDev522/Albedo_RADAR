"""Tests for slot notification rules."""

from app.chain_reader.commitment_classifier import CommitmentType
from app.chain_reader.slot_commitment_scanner import SlotStatus
from app.notifications.slot_rules import is_slot_purchase, should_notify_slot_new


def _slot(
    *,
    uid: int = 1,
    block: int | None = None,
    ctype: CommitmentType = CommitmentType.V7,
    detail: str | None = "ns/model",
    payload_hash: str | None = "hash",
) -> SlotStatus:
    return SlotStatus(
        netuid=97,
        uid=uid,
        hotkey="hk",
        coldkey="ck",
        registered_at_block=1,
        commitment_type=ctype,
        commit_block=block,
        deposit=0,
        reveal_round=None,
        detail=detail,
        reveal_string="",
        payload_hash=payload_hash,
        encrypted_hash=None,
    )


def test_is_slot_purchase_none_to_block():
    slot = _slot(block=8520068, detail="foremost/model")
    previous = {"commit_block": None, "commitment_type": "none", "payload_hash": None, "detail": None}
    assert is_slot_purchase(previous, slot) is True


def test_is_slot_purchase_block_to_block_false():
    slot = _slot(block=8520100)
    previous = {"commit_block": 8520068, "commitment_type": "v7", "payload_hash": "old", "detail": "m"}
    assert is_slot_purchase(previous, slot) is False


def test_is_slot_purchase_block_to_none_false():
    slot = _slot(block=None, ctype=CommitmentType.NONE, detail=None, payload_hash=None)
    previous = {"commit_block": 8520068, "commitment_type": "v7", "payload_hash": "old", "detail": "m"}
    assert is_slot_purchase(previous, slot) is False


def test_should_notify_slot_new_requires_block():
    assert should_notify_slot_new(_slot(block=None, ctype=CommitmentType.NONE, detail=None, payload_hash=None)) is False
    assert should_notify_slot_new(_slot(block=100)) is True
