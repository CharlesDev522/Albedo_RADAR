"""Tests for Hippius latest repos service."""

from datetime import datetime, timezone

import pytest

from app.integrations.hippius_hub_client import HippiusHubModel
from app.services.hippius_latest_service import fetch_latest_hippius_repos


class _FakeHub:
    async def fetch_albedo_index(self, client=None):
        return {
            "a/albedo-qwen3.6-35b-old": HippiusHubModel(
                repo="a/albedo-qwen3.6-35b-old",
                digest="sha256:old",
                primary_tag="main",
                indexed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                file_count=1,
                total_size_bytes=1,
            ),
            "b/albedo-qwen3.6-35b-new": HippiusHubModel(
                repo="b/albedo-qwen3.6-35b-new",
                digest="sha256:new",
                primary_tag="main",
                indexed_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
                file_count=2,
                total_size_bytes=2,
            ),
            "c/other-model": HippiusHubModel(
                repo="c/other-model",
                digest="sha256:x",
                primary_tag="main",
                indexed_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
                file_count=1,
                total_size_bytes=1,
            ),
        }


@pytest.mark.asyncio
async def test_fetch_latest_hippius_repos_sorts_by_index_time(monkeypatch):
    monkeypatch.setattr(
        "app.services.hippius_latest_service.HippiusHubClient",
        lambda settings=None: _FakeHub(),
    )
    total, repos = await fetch_latest_hippius_repos(limit=10)
    assert total == 2
    assert [r.repo for r in repos] == [
        "b/albedo-qwen3.6-35b-new",
        "a/albedo-qwen3.6-35b-old",
    ]
