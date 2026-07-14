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

    from app.integrations.huggingface_registry import HuggingFaceSnapshot

    async def fake_search(self, query, *, limit=100, client=None):
        return [
            "miner/albedo-qwen3.6-35b-test",
            "miner/random-model",
        ]

    async def fake_fetch_model(self, repo, client=None):
        if repo == "miner/random-model":
            return None
        return HuggingFaceSnapshot(
            repo=repo,
            revision="abc123def456",
            commit_sha="revision:abc123def456",
            commit_message=None,
            created_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
            files=(),
        )

    monkeypatch.setattr(
        "app.services.huggingface_latest_service.HuggingFaceRegistryClient.search_models",
        fake_search,
    )
    monkeypatch.setattr(
        "app.services.huggingface_latest_service.HuggingFaceRegistryClient.fetch_model",
        fake_fetch_model,
    )

    total, repos = asyncio.run(fetch_latest_huggingface_repos(limit=5))
    assert total == 1
    assert len(repos) == 1
    assert repos[0].repo == "miner/albedo-qwen3.6-35b-test"
    assert repos[0].hub_url.endswith("/tree/abc123def456")
