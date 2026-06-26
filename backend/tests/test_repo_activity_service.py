"""Tests for merged repo activity sorting."""

from datetime import datetime, timezone

from app.schemas.repo_activity import RepoTrackEntry
from app.services.repo_activity_service import _sort_tracks_latest_first


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
