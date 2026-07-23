"""Tests for GitHub watch API routes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.routes.github_watch import sync_github_watch


def test_sync_github_watch_commits_and_returns_stats():
    mock_stats = {"targets": 1, "new_commits": 0, "seeded": 1, "errors": 0, "slack_sent": 0}
    db = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    settings = MagicMock()

    async def run():
        with patch(
            "app.api.routes.github_watch.GithubRepoWatcher.enabled",
            new_callable=MagicMock,
            return_value=True,
        ), patch(
            "app.api.routes.github_watch.GithubRepoWatcher.sync_once",
            new_callable=AsyncMock,
            return_value=mock_stats,
        ) as sync_mock, patch(
            "app.api.routes.github_watch.GithubRepoWatcher.close",
            new_callable=AsyncMock,
        ) as close_mock:
            result = await sync_github_watch(db=db, settings=settings)

        assert result == {"status": "ok", **mock_stats}
        sync_mock.assert_awaited_once_with(db)
        db.flush.assert_awaited_once()
        close_mock.assert_awaited_once()

    asyncio.run(run())


def test_sync_github_watch_disabled_returns_400():
    db = AsyncMock()
    settings = MagicMock()

    async def run():
        with patch("app.api.routes.github_watch.GithubRepoWatcher") as watcher_cls:
            watcher = watcher_cls.return_value
            watcher.enabled = False
            watcher.close = AsyncMock()
            with pytest.raises(HTTPException) as exc:
                await sync_github_watch(db=db, settings=settings)
            assert exc.value.status_code == 400

    asyncio.run(run())
