"""Read-only Hugging Face Hub API client."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

import httpx

from app.config import Settings, get_settings
from app.integrations.huggingface_search_config import HF_SORT_CREATED_AT, VALID_HF_SORTS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HuggingFaceSearchHit:
    repo: str
    created_at: datetime | None
    last_modified: datetime | None = None
    downloads: int = 0
    likes: int = 0
    tags: tuple[str, ...] = ()


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
        sort: str = HF_SORT_CREATED_AT,
        direction: int = -1,
        tags: Sequence[str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> list[str]:
        """Return model ids from Hugging Face Hub search."""
        hits = await self.search_models_hits(
            query,
            limit=limit,
            sort=sort,
            direction=direction,
            tags=tags,
            client=client,
        )
        return [h.repo for h in hits]

    async def search_models_hits(
        self,
        query: str,
        *,
        limit: int = 100,
        sort: str = HF_SORT_CREATED_AT,
        direction: int = -1,
        tags: Sequence[str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> list[HuggingFaceSearchHit]:
        """Hub search with HF-native sort and optional tag filters (AND)."""
        sort_key = sort if sort in VALID_HF_SORTS else HF_SORT_CREATED_AT
        url = f"{self.base_url}/models"
        params: list[tuple[str, str]] = [
            ("search", query),
            ("limit", str(limit)),
            ("sort", sort_key),
            ("direction", str(direction)),
        ]
        for tag in tags or ():
            tag = tag.strip()
            if tag:
                params.append(("filter", tag))
        resp = await self._request("GET", url, client=client, params=params)
        data = resp.json()
        if not isinstance(data, list):
            return []
        required_tags = [t.strip().lower() for t in (tags or ()) if t.strip()]
        hits: list[HuggingFaceSearchHit] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            model_id = item.get("modelId") or item.get("id")
            if not isinstance(model_id, str) or "/" not in model_id:
                continue
            item_tags = tuple(str(t) for t in (item.get("tags") or []) if t)
            if required_tags and not _tags_include_all(item_tags, required_tags):
                continue
            hits.append(
                HuggingFaceSearchHit(
                    repo=model_id,
                    created_at=_parse_hf_datetime(item.get("createdAt")),
                    last_modified=_parse_hf_datetime(item.get("lastModified")),
                    downloads=int(item.get("downloads") or 0),
                    likes=int(item.get("likes") or 0),
                    tags=item_tags,
                )
            )
        return hits

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
        params: dict[str, str] | list[tuple[str, str]] | None = None,
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


def _parse_hf_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _tags_include_all(item_tags: Sequence[str], required: Sequence[str]) -> bool:
    normalized = {t.lower() for t in item_tags}
    return all(tag in normalized for tag in required)


def hit_sort_value(hit: HuggingFaceSearchHit, sort: str) -> float:
    if sort == "lastModified":
        dt = hit.last_modified or hit.created_at
        return dt.timestamp() if dt else 0.0
    if sort == "downloads":
        return float(hit.downloads)
    if sort == "likes":
        return float(hit.likes)
    dt = hit.created_at
    return dt.timestamp() if dt else 0.0


def _parse_revision(repo: str, revision: str, data: dict[str, Any]) -> HuggingFaceSnapshot:
    sha = str(data.get("sha") or revision)
    commit_message = None
    created_at = _parse_hf_datetime(data.get("lastModified"))

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
