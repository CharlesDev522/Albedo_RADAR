"""Tests for GitHub watch API routes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.routes.github_watch import sync_github_watch


def test_sync_github_watch_commits_and_returns_stats():
    mock_stats = {"targets": 1, "new_commits": 0, "seeded": 1, "errors": 0, "slack_sent": 0}
    db = AsyncMock()
    db.commit = AsyncMock()
    settings = MagicMock()

    async def run():
        with patch(
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
        db.commit.assert_awaited_once()
        close_mock.assert_awaited_once()

    asyncio.run(run())
