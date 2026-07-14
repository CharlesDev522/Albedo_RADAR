"""GitHub REST API client for commit polling."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_GITHUB_TREE_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tree/(?P<branch>.+?)/?$",
    re.IGNORECASE,
)
_GITHUB_REPO_RE = re.compile(r"^(?P<owner>[^/]+)/(?P<repo>[^/@]+)(?:@(?P<branch>.+))?$")


@dataclass(frozen=True)
class GithubWatchTarget:
    owner: str
    repo: str
    branch: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def tree_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}/tree/{self.branch}"


@dataclass(frozen=True)
class GithubCommit:
    sha: str
    short_sha: str
    subject: str
    body: str
    author_name: str | None
    committed_at: datetime | None
    html_url: str

    @property
    def short_body(self) -> str:
        body = self.body.strip()
        if not body:
            return ""
        if len(body) <= 240:
            return body
        return f"{body[:237]}…"


def parse_github_watch_spec(spec: str) -> GithubWatchTarget:
    """Parse owner/repo@branch or a github.com/.../tree/branch URL."""
    raw = spec.strip()
    if not raw:
        raise ValueError("empty github watch spec")

    tree_match = _GITHUB_TREE_RE.match(raw)
    if tree_match:
        return GithubWatchTarget(
            owner=tree_match.group("owner"),
            repo=tree_match.group("repo"),
            branch=tree_match.group("branch"),
        )

    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2:
            branch = parts[2] if len(parts) >= 3 and parts[2] != "tree" else "main"
            if len(parts) >= 4 and parts[2] == "tree":
                branch = parts[3]
            return GithubWatchTarget(owner=parts[0], repo=parts[1], branch=branch)
        raise ValueError(f"unsupported github URL: {spec}")

    repo_match = _GITHUB_REPO_RE.match(raw)
    if not repo_match:
        raise ValueError(f"unsupported github watch spec: {spec}")

    branch = repo_match.group("branch") or "main"
    return GithubWatchTarget(
        owner=repo_match.group("owner"),
        repo=repo_match.group("repo"),
        branch=branch,
    )


def parse_github_watch_specs(specs: list[str]) -> list[GithubWatchTarget]:
    targets: list[GithubWatchTarget] = []
    seen: set[tuple[str, str, str]] = set()
    for spec in specs:
        if not spec.strip():
            continue
        target = parse_github_watch_spec(spec)
        key = (target.owner, target.repo, target.branch)
        if key in seen:
            continue
        seen.add(key)
        targets.append(target)
    return targets


def _parse_commit(payload: dict[str, Any]) -> GithubCommit:
    commit = payload.get("commit") or {}
    message = str(commit.get("message") or "")
    lines = message.splitlines()
    subject = lines[0].strip() if lines else message.strip() or "(no message)"
    body = "\n".join(lines[1:]).strip()
    author = commit.get("author") or {}
    committed_at: datetime | None = None
    if author.get("date"):
        try:
            committed_at = datetime.fromisoformat(str(author["date"]).replace("Z", "+00:00"))
        except ValueError:
            committed_at = None
    sha = str(payload.get("sha") or "")
    return GithubCommit(
        sha=sha,
        short_sha=sha[:7] if sha else "?",
        subject=subject,
        body=body,
        author_name=(author.get("name") or None),
        committed_at=committed_at,
        html_url=str(payload.get("html_url") or ""),
    )


class GithubClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": self.settings.app_name,
        }
        token = (self.settings.github_token or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def fetch_commits(
        self,
        target: GithubWatchTarget,
        *,
        client: httpx.AsyncClient,
        per_page: int = 10,
    ) -> list[GithubCommit]:
        url = f"{self.settings.github_api_url.rstrip('/')}/repos/{target.owner}/{target.repo}/commits"
        resp = await client.get(
            url,
            params={"sha": target.branch, "per_page": per_page},
            headers=self._headers(),
        )
        if resp.status_code == 404:
            logger.warning("github repo not found %s branch=%s", target.full_name, target.branch)
            return []
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            return []
        return [_parse_commit(item) for item in payload if isinstance(item, dict)]
