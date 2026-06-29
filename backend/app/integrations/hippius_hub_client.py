"""Hippius Hub model index API (api.hippius.com) — mirrors hub.hippius.com search."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.integrations.hippius_registry import normalize_digest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HippiusHubModel:
    repo: str
    digest: str
    primary_tag: str
    indexed_at: datetime | None
    file_count: int | None
    total_size_bytes: int | None


def _parse_indexed_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_model_row(row: dict[str, Any]) -> HippiusHubModel | None:
    project = str(row.get("project") or "").strip()
    name = str(row.get("repo") or "").strip()
    if not project or not name:
        return None
    digest = normalize_digest(str(row.get("digest") or ""))
    if not digest:
        return None
    return HippiusHubModel(
        repo=f"{project}/{name}",
        digest=digest,
        primary_tag=str(row.get("primary_tag") or "main"),
        indexed_at=_parse_indexed_at(row.get("indexed_at")),
        file_count=int(row["file_count"]) if row.get("file_count") is not None else None,
        total_size_bytes=int(row["total_size_bytes"])
        if row.get("total_size_bytes") is not None
        else None,
    )


class HippiusHubClient:
    """Read-only client for https://api.hippius.com/api/models/ (Hippius Hub index)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.hippius_hub_api_url.rstrip("/")

    async def search_page(
        self,
        query: str,
        *,
        page: int = 1,
        page_size: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> tuple[list[HippiusHubModel], int]:
        page_size = page_size or self.settings.hippius_hub_page_size
        url = f"{self.base_url}/"
        params = {"q": query, "page": str(page), "page_size": str(page_size)}

        async def _do(c: httpx.AsyncClient) -> tuple[list[HippiusHubModel], int]:
            resp = await c.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            total = int(data.get("total") or 0)
            rows = data.get("results") or []
            models: list[HippiusHubModel] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                parsed = _parse_model_row(row)
                if parsed:
                    models.append(parsed)
            return models, total

        if client is not None:
            return await _do(client)
        timeout = self.settings.market_http_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as c:
            return await _do(c)

    async def fetch_albedo_index(
        self,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, HippiusHubModel]:
        """Merge all configured hub search queries into one repo → latest-index entry map."""
        merged: dict[str, HippiusHubModel] = {}
        queries = self.settings.hippius_hub_search_queries or ("albedo",)

        async def _search_all(query: str) -> None:
            page = 1
            max_pages = max(self.settings.hippius_hub_max_pages, 1)
            total = None
            while page <= max_pages:
                models, reported_total = await self.search_page(
                    query, page=page, client=client
                )
                if total is None:
                    total = reported_total
                if not models:
                    break
                for model in models:
                    existing = merged.get(model.repo)
                    if existing is None:
                        merged[model.repo] = model
                        continue
                    existing_ts = existing.indexed_at
                    model_ts = model.indexed_at
                    if model_ts and (existing_ts is None or model_ts > existing_ts):
                        merged[model.repo] = model
                if total is not None and page * self.settings.hippius_hub_page_size >= total:
                    break
                page += 1

        for query in queries:
            q = str(query).strip()
            if not q:
                continue
            try:
                await _search_all(q)
            except Exception:
                logger.warning("hippius hub search failed q=%s", q, exc_info=True)

        return merged
