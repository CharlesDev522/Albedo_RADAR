"""Read-only Hugging Face Hub API client."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HuggingFaceFile:
    name: str
    digest: str
    size: int


@dataclass(frozen=True)
class HuggingFaceSnapshot:
    repo: str
    revision: str
    commit_sha: str
    commit_message: str | None
    created_at: datetime | None
    files: tuple[HuggingFaceFile, ...]

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)


class HuggingFaceRegistryClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.huggingface_api_url.rstrip("/")

    async def fetch_revision(
        self,
        repo: str,
        revision: str,
        client: httpx.AsyncClient | None = None,
    ) -> HuggingFaceSnapshot | None:
        url = f"{self.base_url}/models/{repo}/revision/{revision}"
        resp = await self._request("GET", url, client=client)
        data = resp.json()
        return _parse_revision(repo, revision, data)

    async def search_models(
        self,
        query: str,
        *,
        limit: int = 100,
        client: httpx.AsyncClient | None = None,
    ) -> list[str]:
        """Return model ids from Hugging Face Hub search."""
        url = f"{self.base_url}/models"
        params = {"search": query, "limit": str(limit)}
        resp = await self._request("GET", url, client=client, params=params)
        data = resp.json()
        if not isinstance(data, list):
            return []
        repos: list[str] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            model_id = item.get("modelId") or item.get("id")
            if isinstance(model_id, str) and "/" in model_id:
                repos.append(model_id)
        return repos

    async def fetch_model(
        self,
        repo: str,
        client: httpx.AsyncClient | None = None,
    ) -> HuggingFaceSnapshot | None:
        url = f"{self.base_url}/models/{repo}"
        resp = await self._request("GET", url, client=client)
        data = resp.json()
        sha = data.get("sha")
        if not sha:
            return None
        return _parse_revision(repo, sha, data)

    async def list_author_models(
        self,
        author: str,
        *,
        limit: int = 100,
        client: httpx.AsyncClient | None = None,
    ) -> list[str]:
        url = f"{self.base_url}/models"
        params = {"author": author, "limit": str(limit)}
        resp = await self._request("GET", url, client=client, params=params)
        data = resp.json()
        if not isinstance(data, list):
            return []
        repos: list[str] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            model_id = item.get("modelId") or item.get("id")
            if isinstance(model_id, str) and "/" in model_id:
                repos.append(model_id)
        return repos

    async def list_commits(
        self,
        repo: str,
        revision: str | None = None,
        *,
        limit: int = 5,
        client: httpx.AsyncClient | None = None,
    ) -> list[dict[str, Any]]:
        rev = revision or "main"
        url = f"{self.base_url}/models/{repo}/commits/{rev}"
        params = {"limit": str(limit)}
        resp = await self._request("GET", url, client=client, params=params)
        data = resp.json()
        return data if isinstance(data, list) else []

    async def _request(
        self,
        method: str,
        url: str,
        client: httpx.AsyncClient | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        timeout = self.settings.market_http_timeout_seconds
        headers = {"User-Agent": "MinerWatch/1.0"}

        async def _do(c: httpx.AsyncClient) -> httpx.Response:
            resp = await c.request(method, url, headers=headers, params=params)
            resp.raise_for_status()
            return resp

        if client is not None:
            return await _do(client)
        async with httpx.AsyncClient(timeout=timeout) as c:
            return await _do(c)


def _parse_revision(repo: str, revision: str, data: dict[str, Any]) -> HuggingFaceSnapshot:
    sha = str(data.get("sha") or revision)
    commit_message = None
    last_modified = data.get("lastModified")
    created_at: datetime | None = None
    if last_modified:
        try:
            created_at = datetime.fromisoformat(str(last_modified).replace("Z", "+00:00"))
        except ValueError:
            created_at = None

    files: list[HuggingFaceFile] = []
    for sibling in data.get("siblings") or []:
        if not isinstance(sibling, dict):
            continue
        name = str(sibling.get("rfilename") or sibling.get("path") or "unknown")
        oid = str(sibling.get("oid") or sibling.get("lfs", {}).get("oid") or "")
        size = int(sibling.get("size") or 0)
        files.append(HuggingFaceFile(name=name, digest=oid, size=size))

    files.sort(key=lambda f: f.name)
    return HuggingFaceSnapshot(
        repo=repo,
        revision=revision,
        commit_sha=f"revision:{sha}",
        commit_message=commit_message,
        created_at=created_at,
        files=tuple(files),
    )
