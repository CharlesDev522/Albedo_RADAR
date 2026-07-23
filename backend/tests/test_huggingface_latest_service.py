"""Tests for Hugging Face latest repo discovery."""

import asyncio

from app.services.huggingface_latest_service import fetch_latest_huggingface_repos, huggingface_browse_url


def test_huggingface_browse_url():
    assert huggingface_browse_url("owner/repo") == "https://huggingface.co/owner/repo"
    assert (
        huggingface_browse_url("owner/repo", "revision:abc123")
        == "https://huggingface.co/owner/repo/tree/abc123"
    )


def test_fetch_latest_huggingface_repos_filters_albedo(monkeypatch):
    from datetime import datetime, timezone

    from app.integrations.huggingface_registry import HuggingFaceSearchHit

    async def fake_search_hits(self, query, *, limit=100, sort="createdAt", direction=-1, tags=None, client=None):
        return [
            HuggingFaceSearchHit(
                repo="miner/albedo-qwen3.6-35b-test",
                created_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
            ),
            HuggingFaceSearchHit(repo="miner/random-model", created_at=None),
        ]

    monkeypatch.setattr(
        "app.services.huggingface_latest_service.HuggingFaceRegistryClient.search_models_hits",
        fake_search_hits,
    )

    total, repos = asyncio.run(fetch_latest_huggingface_repos(limit=5, force_refresh=True))
    assert total == 1
    assert len(repos) == 1
    assert repos[0].repo == "miner/albedo-qwen3.6-35b-test"
    assert repos[0].hub_url == "https://huggingface.co/miner/albedo-qwen3.6-35b-test"


def test_fetch_latest_huggingface_repos_orders_by_created_date(monkeypatch):
    from datetime import datetime, timezone

    from app.integrations.huggingface_registry import HuggingFaceSearchHit

    async def fake_search_hits(self, query, *, limit=100, sort="createdAt", direction=-1, tags=None, client=None):
        return [
            HuggingFaceSearchHit(
                repo="a/miner/albedo-qwen3-4b-old",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            HuggingFaceSearchHit(
                repo="b/miner/albedo-qwen3.6-35b-new",
                created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            ),
        ]

    monkeypatch.setattr(
        "app.services.huggingface_latest_service.HuggingFaceRegistryClient.search_models_hits",
        fake_search_hits,
    )

    _, repos = asyncio.run(fetch_latest_huggingface_repos(limit=2, sort="createdAt", force_refresh=True))
    assert [r.repo for r in repos] == [
        "b/miner/albedo-qwen3.6-35b-new",
        "a/miner/albedo-qwen3-4b-old",
    ]


def test_fetch_latest_huggingface_repos_applies_tracked_status(monkeypatch):
    from datetime import datetime, timezone

    from app.integrations.huggingface_registry import HuggingFaceSearchHit
    from app.schemas.repo_activity import RepoTrackEntry

    async def fake_search_hits(self, query, *, limit=100, sort="createdAt", direction=-1, tags=None, client=None):
        return [
            HuggingFaceSearchHit(
                repo="miner/albedo-qwen3.6-35b-test",
                created_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
            ),
        ]

    monkeypatch.setattr(
        "app.services.huggingface_latest_service.HuggingFaceRegistryClient.search_models_hits",
        fake_search_hits,
    )

    tracked = [
        RepoTrackEntry(
            id=1,
            subnet=97,
            repo="miner/albedo-qwen3.6-35b-test",
            repo_host="huggingface",
            uid=None,
            hotkey="hub:huggingface:miner/albedo-qwen3.6-35b-test",
            coldkey=None,
            model_family="qwen3.6-35b",
            chain_digest=None,
            hub_digest="revision:sha",
            hub_revision="main",
            hub_commit_message=None,
            hub_updated_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
            file_count=1,
            total_bytes=10,
            digest_in_sync=True,
            last_checked_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
            last_hub_change_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
            first_tracked_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
            last_updated=datetime(2026, 7, 10, tzinfo=timezone.utc),
            pending_hub_poll=False,
            track_source="hub_watch",
        )
    ]

    _, repos = asyncio.run(
        fetch_latest_huggingface_repos(limit=1, tracked_entries=tracked, force_refresh=True)
    )
    assert repos[0].is_tracked is True
    assert repos[0].digest_in_sync is True
    assert repos[0].digest == "revision:sha"


def test_fetch_latest_huggingface_repos_uses_cache(monkeypatch):
    from datetime import datetime, timezone

    from app.integrations.huggingface_registry import HuggingFaceSearchHit
    from app.services import hf_latest_cache

    calls = {"n": 0}

    async def fake_search_hits(self, query, *, limit=100, sort="createdAt", direction=-1, tags=None, client=None):
        calls["n"] += 1
        return [
            HuggingFaceSearchHit(
                repo="miner/albedo-qwen3.6-35b-test",
                created_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
            ),
        ]

    monkeypatch.setattr(
        "app.services.huggingface_latest_service.HuggingFaceRegistryClient.search_models_hits",
        fake_search_hits,
    )
    hf_latest_cache._store.clear()

    asyncio.run(fetch_latest_huggingface_repos(limit=5, force_refresh=True))
    asyncio.run(fetch_latest_huggingface_repos(limit=5, force_refresh=False))
    assert calls["n"] == 2
