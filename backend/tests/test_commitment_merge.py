"""Model commit merge — timelock must block stale revealed v6."""

from app.chain_reader.commitment_scanner import _merge_model_commit_sources


def test_timelock_blocks_revealed_v6_fallback():
    active: dict[str, tuple[int, str]] = {}
    revealed = {"hk1": (1_000_000, "v6|org/model|sha256:abc")}
    timelock = {"hk1"}
    merged = _merge_model_commit_sources(active, revealed, timelock)
    assert "hk1" not in merged


def test_revealed_v6_used_when_no_timelock():
    active: dict[str, tuple[int, str]] = {}
    revealed = {"hk1": (1_000_000, "v6|org/model|sha256:abc123deadbeef")}
    merged = _merge_model_commit_sources(active, revealed, set())
    assert merged["hk1"][1].startswith("v6|")
    assert merged["hk1"][2] == "revealed"


def test_active_new_payload_wins_over_stale_revealed():
    active = {"hk1": (2_100_000, "v6|org/new-model|sha256:newhash")}
    revealed = {"hk1": (2_200_000, "v6|org/old-model|sha256:oldhash")}
    merged = _merge_model_commit_sources(active, revealed, set())
    assert merged["hk1"][1].startswith("v6|org/new-model")
    assert merged["hk1"][0] == 2_100_000
    assert merged["hk1"][2] == "active"


def test_revealed_refines_block_for_same_payload():
    active = {"hk1": (2_000_000, "v6|org/model|sha256:abc123deadbeef")}
    revealed = {"hk1": (2_100_000, "v6|org/model|sha256:abc123deadbeef")}
    merged = _merge_model_commit_sources(active, revealed, set())
    assert merged["hk1"][0] == 2_100_000
    assert merged["hk1"][2] == "revealed"
