"""Slot status merge — RevealedCommitments must surface v6 like the commits table."""

from app.chain_reader.commitment_classifier import (
    ClassifiedCommitment,
    CommitmentType,
    classify_plaintext_reveal,
)
from app.chain_reader.slot_commitment_scanner import _merge_slot_classifications


def test_revealed_v6_fills_empty_active_slot():
    rev = classify_plaintext_reveal(
        "v6|org/model|sha256:abc",
        commit_block=1_000_000,
    )
    merged = _merge_slot_classifications({}, {"hk1": rev})
    assert merged["hk1"].commitment_type == CommitmentType.V6


def test_timelock_active_not_replaced_by_revealed_v6():
    active = ClassifiedCommitment(
        commitment_type=CommitmentType.TIMELOCK_ENCRYPTED,
        commit_block=2_000_000,
        deposit=0,
        reveal_string=None,
        detail="round:99",
        reveal_round=99,
        encrypted_hash="abc",
        payload_hash="abc",
    )
    rev = classify_plaintext_reveal(
        "v6|org/model|sha256:abc",
        commit_block=1_000_000,
    )
    merged = _merge_slot_classifications({"hk1": active}, {"hk1": rev})
    assert merged["hk1"].commitment_type == CommitmentType.TIMELOCK_ENCRYPTED


def test_revealed_v6_wins_when_block_newer():
    active = classify_plaintext_reveal(
        "v6|org/old|sha256:aaa",
        commit_block=1_000_000,
    )
    rev = classify_plaintext_reveal(
        "v6|org/new|sha256:bbb",
        commit_block=1_500_000,
    )
    merged = _merge_slot_classifications({"hk1": active}, {"hk1": rev})
    assert merged["hk1"].commitment_type == CommitmentType.V6
    assert merged["hk1"].commit_block == 1_500_000


def test_same_reveal_prefers_higher_block_from_revealed():
    active = classify_plaintext_reveal(
        "v6|org/model|sha256:abc",
        commit_block=999_000,
    )
    rev = classify_plaintext_reveal(
        "v6|org/model|sha256:abc",
        commit_block=1_000_000,
    )
    merged = _merge_slot_classifications({"hk1": active}, {"hk1": rev})
    assert merged["hk1"].commit_block == 1_000_000
