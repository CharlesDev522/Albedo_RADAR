"""Latest repos from Hippius Hub index (live api.hippius.com)."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.chain_reader.albedo_model_family import FAMILY_QWEN36_35B, FAMILY_QWEN3_4B, infer_albedo_model_family
from app.config import Settings, get_settings
from app.integrations.hippius_hub_client import HippiusHubClient
from app.processing.priority_miner_discovery import hippius_browse_url
from app.schemas.repo_activity import HippiusLatestRepo


async def fetch_latest_hippius_repos(
    *,
    limit: int = 10,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[int, list[HippiusLatestRepo]]:
    settings = settings or get_settings()
    hub = HippiusHubClient(settings)
    index = await hub.fetch_albedo_index(client=client)

    models = [
        m
        for m in index.values()
        if infer_albedo_model_family(m.repo) in (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B)
    ]
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    models.sort(key=lambda m: m.indexed_at or epoch, reverse=True)

    repos = [
        HippiusLatestRepo(
            repo=m.repo,
            model_family=infer_albedo_model_family(m.repo),
            digest=m.digest,
            indexed_at=m.indexed_at,
            file_count=m.file_count,
            total_size_bytes=m.total_size_bytes,
            hub_url=hippius_browse_url(m.repo, m.primary_tag),
        )
        for m in models[: max(limit, 1)]
    ]
    return len(models), repos
