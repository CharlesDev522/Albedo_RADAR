"""API route helpers for repo activity."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes.repo_activity import _event_to_response, hippius_latest_repos


def test_event_to_response_coalesces_null_json():
    row = MagicMock()
    row.id = 1
    row.subnet = 97
    row.event_type = "hub_repo_added"
    row.repo = "miner/albedo-qwen3.6-35b-a"
    row.uid = 3
    row.hotkey = "hk"
    row.coldkey = None
    row.model_family = "qwen3.6-35b"
    row.chain_digest = None
    row.hub_digest = "sha256:abc"
    row.previous_digest = None
    row.revision = "main"
    row.commit_block = None
    row.commit_message = None
    row.changed_files = None
    row.detected_at = datetime(2026, 6, 14, tzinfo=timezone.utc)
    row.meta = None

    resp = _event_to_response(row)
    assert resp.changed_files == []
    assert resp.meta == {}


@pytest.mark.asyncio
async def test_hippius_latest_returns_empty_on_fetch_error(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.repo_activity.fetch_latest_hippius_repos",
        AsyncMock(side_effect=RuntimeError("hub down")),
    )
    result = await hippius_latest_repos(limit=10)
    assert result.total_indexed == 0
    assert result.repos == []


@pytest.mark.asyncio
async def test_huggingface_latest_returns_error_on_fetch_error(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.repo_activity.fetch_latest_huggingface_repos",
        AsyncMock(side_effect=RuntimeError("hub down")),
    )
    monkeypatch.setattr(
        "app.api.routes.repo_activity.merged_repo_tracks",
        AsyncMock(return_value=[]),
    )
    from app.api.routes.repo_activity import huggingface_latest_repos

    result = await huggingface_latest_repos(
        limit=10, sort="createdAt", tags=None, subnet=97, force_refresh=False, db=AsyncMock()
    )
    assert result.total_indexed == 0
    assert result.repos == []
    assert result.error == "hub down"
