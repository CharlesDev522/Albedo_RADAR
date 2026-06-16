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


def test_active_v6_uses_on_chain_block():
    active = {"hk1": (2_000_000, "v6|org/model|sha256:abc123deadbeef")}
    revealed = {"hk1": (1_000_000, "v6|org/model|sha256:abc123deadbeef")}
    merged = _merge_model_commit_sources(active, revealed, set())
    assert merged["hk1"][0] == 2_000_000
    assert merged["hk1"][2] == "active"
