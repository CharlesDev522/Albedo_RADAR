"""Slack delivery for GitHub commit alerts."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings
from app.integrations.github_client import GithubCommit, GithubWatchTarget

logger = logging.getLogger(__name__)


def _slack_channel(channel: str | None) -> str | None:
    if not channel:
        return None
    c = channel.strip()
    if c.startswith("#") or c.startswith("C"):
        return c
    return f"#{c}"


def format_github_commit_alert(
    target: GithubWatchTarget,
    commit: GithubCommit,
) -> tuple[str, str, dict[str, Any]]:
    title = f"[github] {target.repo}@{target.branch} — {commit.short_sha}"
    message = commit.subject
    detail = {
        "repo": target.full_name,
        "branch": target.branch,
        "commit_sha": commit.sha,
        "commit_short_sha": commit.short_sha,
        "commit_subject": commit.subject,
        "commit_body": commit.short_body,
        "commit_url": commit.html_url,
        "author": commit.author_name,
        "committed_at": commit.committed_at.isoformat() if commit.committed_at else None,
        "tree_url": target.tree_url,
    }
    return title, message, detail


def format_slack_body(target: GithubWatchTarget, commit: GithubCommit) -> str:
    lines = [
        f"*Repo:* <{target.tree_url}|{target.full_name}> (`{target.branch}`)",
        f"*Commit:* `{commit.short_sha}` — {commit.subject}",
    ]
    if commit.short_body:
        lines.append(f"*Message:*\n>{commit.short_body.replace(chr(10), chr(10) + '> ')}")
    if commit.author_name:
        lines.append(f"*Author:* {commit.author_name}")
    lines.append(f"*URL:* <{commit.html_url}|open on GitHub>")
    return "\n".join(lines)


async def send_github_commit_slack(
    *,
    settings: Settings,
    target: GithubWatchTarget,
    commit: GithubCommit,
    client: httpx.AsyncClient | None = None,
) -> bool:
    webhook = (settings.slack_webhook_url or "").strip()
    if not webhook:
        return False

    header = f":github: {target.repo} `{target.branch}` — {commit.short_sha}"
    body = format_slack_body(target, commit)
    payload: dict[str, Any] = {
        "text": f"{header}\n{commit.subject}\n{commit.html_url}",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": header[:150]}},
            {"type": "section", "text": {"type": "mrkdwn", "text": body[:3000]}},
        ],
    }
    channel = _slack_channel(settings.slack_channel)
    if channel:
        payload["channel"] = channel
    if settings.slack_app_name:
        payload["username"] = settings.slack_app_name

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=settings.market_http_timeout_seconds)
    try:
        resp = await http.post(webhook, json=payload)
        if resp.status_code >= 400:
            logger.error("github slack webhook HTTP %s body=%s", resp.status_code, resp.text[:500])
            return False
        return True
    except Exception:
        logger.exception("github slack webhook failed repo=%s sha=%s", target.full_name, commit.sha)
        return False
    finally:
        if owns_client:
            await http.aclose()
