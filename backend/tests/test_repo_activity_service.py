"""Tests for merged repo activity sorting and hub-first merge."""

from datetime import datetime, timezone

from app.db.models import HippiusRepoTrack, MinerCommitment, MinerSlotStatus
from app.schemas.repo_activity import RepoTrackEntry
from app.services.repo_activity_service import (
    _sort_tracks_latest_first,
    build_merged_repo_tracks,
)


def _entry(**kwargs) -> RepoTrackEntry:
    now = datetime.now(timezone.utc)
    base = dict(
        id=1,
        subnet=97,
        repo="miner/albedo-qwen3.6-35b-a",
        repo_host="hippius",
        uid=1,
        hotkey="hk1",
        coldkey=None,
        model_family="qwen3.6-35b",
        chain_digest=None,
        hub_digest=None,
        hub_revision="main",
        hub_commit_message=None,
        hub_updated_at=None,
        file_count=None,
        total_bytes=None,
        digest_in_sync=None,
        last_checked_at=None,
        last_hub_change_at=None,
        first_tracked_at=now,
        last_updated=now,
    )
    base.update(kwargs)
    return RepoTrackEntry(**base)


def test_sort_tracks_latest_first():
    old = datetime(2026, 6, 1, tzinfo=timezone.utc)
    mid = datetime(2026, 6, 10, tzinfo=timezone.utc)
    new = datetime(2026, 6, 14, tzinfo=timezone.utc)

    entries = [
        _entry(id=1, hub_updated_at=old),
        _entry(id=2, last_hub_change_at=new, repo="b/b"),
        _entry(id=3, hub_updated_at=mid, repo="c/c"),
    ]
    sorted_entries = _sort_tracks_latest_first(entries)
    assert [e.id for e in sorted_entries] == [2, 3, 1]


def test_sort_puts_definite_remote_time_before_uncertain():
    definite_old = datetime(2026, 6, 1, tzinfo=timezone.utc)
    uncertain_new = datetime(2026, 6, 20, tzinfo=timezone.utc)

    entries = [
        _entry(id=1, last_checked_at=uncertain_new),
        _entry(id=2, hub_updated_at=definite_old, repo="b/b"),
    ]
    sorted_entries = _sort_tracks_latest_first(entries)
    assert [e.id for e in sorted_entries] == [2, 1]


def test_hub_first_merge_shows_slot_without_commitment():
    now = datetime.now(timezone.utc)
    slot = MinerSlotStatus(
        id=1,
        subnet=97,
        uid=12,
        hotkey="slot_hotkey",
        coldkey="cold",
        commitment_type="v7",
        detail="miner/albedo-qwen3.6-35b-alpha",
        last_updated=now,
    )
    merged = build_merged_repo_tracks(slots=[slot], commits=[], tracks=[])
    assert len(merged) == 1
    assert merged[0].uid == 12
    assert merged[0].track_source == "slot"
    assert merged[0].chain_digest is None
    assert merged[0].pending_hub_poll is True


def test_hub_first_merge_overlays_commit_on_slot():
    now = datetime.now(timezone.utc)
    slot = MinerSlotStatus(
        id=1,
        subnet=97,
        uid=3,
        hotkey="hk",
        coldkey="ck",
        commitment_type="v7",
        detail="miner/albedo-qwen3.6-35b-beta",
        last_updated=now,
    )
    commit = MinerCommitment(
        id=10,
        subnet=97,
        uid=3,
        hotkey="hk",
        coldkey="ck",
        commit_block=100,
        reveal_string="x",
        repo="miner/albedo-qwen3.6-35b-beta",
        digest="sha256:abc",
        model_uri="hippius://miner/albedo-qwen3.6-35b-beta",
        payload_hash="ph",
        first_seen=now,
        last_updated=now,
    )
    track = HippiusRepoTrack(
        id=5,
        subnet=97,
        repo="miner/albedo-qwen3.6-35b-beta",
        hotkey="hk",
        uid=3,
        hub_digest="sha256:abc",
        hub_revision="main",
        first_tracked_at=now,
        last_updated=now,
    )
    merged = build_merged_repo_tracks(slots=[slot], commits=[commit], tracks=[track])
    assert len(merged) == 1
    assert merged[0].track_source == "commitment"
    assert merged[0].chain_digest == "sha256:abc"
    assert merged[0].digest_in_sync is True


def test_hub_first_merge_includes_hub_watch_without_uid():
    now = datetime.now(timezone.utc)
    track = HippiusRepoTrack(
        id=9,
        subnet=97,
        repo="org/albedo-qwen3.6-35b-discovered",
        hotkey="hub:org/albedo-qwen3.6-35b-discovered",
        uid=None,
        hub_digest="sha256:zzz",
        hub_revision="main",
        model_family="qwen3.6-35b",
        first_tracked_at=now,
        last_updated=now,
    )
    merged = build_merged_repo_tracks(slots=[], commits=[], tracks=[track])
    assert len(merged) == 1
    assert merged[0].track_source == "hub_watch"
    assert merged[0].uid is None
