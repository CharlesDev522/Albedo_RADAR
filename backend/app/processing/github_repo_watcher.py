"""Poll configured GitHub repos and notify on new commits."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import GithubCommitAlert, GithubRepoWatchState
from app.integrations.github_client import GithubClient, GithubWatchTarget, parse_github_watch_specs
from app.notifications.github_slack import format_github_commit_alert, send_github_commit_slack
from app.notifications.preferences import NotificationPreferencesStore

logger = logging.getLogger(__name__)


class GithubRepoWatcher:
    def __init__(
        self,
        settings: Settings | None = None,
        preferences: NotificationPreferencesStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.preferences = preferences or NotificationPreferencesStore(self.settings)
        self.client = GithubClient(self.settings)
        self._http: httpx.AsyncClient | None = None
        self._seeded: set[str] = set()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.github_repo_tracking_enabled and self.settings.github_repo_watches)

    def targets(self) -> list[GithubWatchTarget]:
        return parse_github_watch_specs(self.settings.github_repo_watches)

    def _http_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.settings.market_http_timeout_seconds)
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _get_state(
        self,
        session: AsyncSession,
        target: GithubWatchTarget,
    ) -> GithubRepoWatchState:
        result = await session.execute(
            select(GithubRepoWatchState).where(
                GithubRepoWatchState.owner == target.owner,
                GithubRepoWatchState.repo == target.repo,
                GithubRepoWatchState.branch == target.branch,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = GithubRepoWatchState(
                owner=target.owner,
                repo=target.repo,
                branch=target.branch,
                tree_url=target.tree_url,
            )
            session.add(row)
            await session.flush()
        return row

    async def sync_once(self, session: AsyncSession) -> dict[str, int]:
        stats = {"targets": 0, "new_commits": 0, "seeded": 0, "errors": 0, "slack_sent": 0}
        if not self.enabled:
            return stats

        http = self._http_client()
        for target in self.targets():
            stats["targets"] += 1
            watch_key = f"{target.owner}/{target.repo}@{target.branch}"
            state: GithubRepoWatchState | None = None
            try:
                state = await self._get_state(session, target)
                commits = await self.client.fetch_commits(target, client=http)
                state.last_checked_at = datetime.now(timezone.utc)
                if not commits:
                    continue

                latest = commits[0]
                state.last_seen_sha = latest.sha
                state.last_commit_subject = latest.subject
                state.last_commit_url = latest.html_url

                if state.seeded_at is None and watch_key not in self._seeded:
                    state.seeded_at = datetime.now(timezone.utc)
                    state.seeded_sha = latest.sha
                    self._seeded.add(watch_key)
                    stats["seeded"] += 1
                    logger.info(
                        "github watch seeded %s@%s at %s (%s)",
                        target.full_name,
                        target.branch,
                        latest.short_sha,
                        latest.subject,
                    )
                    continue

                known_sha = state.seeded_sha or latest.sha
                new_commits = []
                for commit in commits:
                    if commit.sha == known_sha:
                        break
                    new_commits.append(commit)
                if not new_commits:
                    continue

                for commit in reversed(new_commits):
                    source_key = f"github:{target.owner}/{target.repo}:{target.branch}:{commit.sha}"
                    existing = await session.execute(
                        select(GithubCommitAlert.id).where(GithubCommitAlert.source_key == source_key)
                    )
                    if existing.scalar_one_or_none() is not None:
                        continue

                    title, message, detail = format_github_commit_alert(target, commit)
                    row = GithubCommitAlert(
                        owner=target.owner,
                        repo=target.repo,
                        branch=target.branch,
                        commit_sha=commit.sha,
                        commit_subject=commit.subject,
                        commit_body=commit.short_body,
                        commit_url=commit.html_url,
                        source_key=source_key,
                        title=title,
                        message=message,
                        detail=detail,
                        slack_sent=False,
                    )
                    session.add(row)
                    await session.flush()
                    stats["new_commits"] += 1

                    if (
                        self.preferences.notifications_enabled
                        and self.preferences.is_kind_enabled("github_commit")
                        and self.settings.slack_webhook_url
                    ):
                        sent = await send_github_commit_slack(
                            settings=self.settings,
                            target=target,
                            commit=commit,
                            client=http,
                        )
                        row.slack_sent = sent
                        if sent:
                            stats["slack_sent"] += 1
                    logger.info(
                        "github new commit %s@%s %s — %s",
                        target.full_name,
                        target.branch,
                        commit.short_sha,
                        commit.subject,
                    )

                state.seeded_sha = latest.sha
            except Exception:
                stats["errors"] += 1
                if state is not None:
                    state.last_checked_at = datetime.now(timezone.utc)
                logger.exception("github watch failed %s", watch_key)

        await session.flush()
        return stats
