"""Latest Albedo repos from Hugging Face Hub search."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.chain_reader.albedo_model_family import FAMILY_QWEN36_35B, FAMILY_QWEN3_4B, infer_albedo_model_family
from app.config import Settings, get_settings
from app.integrations.huggingface_registry import HuggingFaceRegistryClient
from app.schemas.repo_activity import HuggingFaceLatestRepo

HF_DISCOVERY_QUERIES = ("albedo-qwen3.6-35b", "albedo-qwen3-4b")
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def huggingface_browse_url(repo: str, revision: str | None = None) -> str:
    if revision:
        rev = revision.removeprefix("revision:").removeprefix("hf:")
        return f"https://huggingface.co/{repo}/tree/{rev}"
    return f"https://huggingface.co/{repo}"


def _merge_modified(*values: datetime | None) -> datetime | None:
    valid = [v for v in values if v is not None]
    return max(valid) if valid else None


def _repo_sort_key(repo: HuggingFaceLatestRepo) -> tuple[int, float, str]:
    """Dated repos first, newest first; stable tie-break on repo id."""
    if repo.indexed_at is None:
        return (1, 0.0, repo.repo)
    return (0, -repo.indexed_at.timestamp(), repo.repo)


async def fetch_latest_huggingface_repos(
    *,
    limit: int = 10,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[int, list[HuggingFaceLatestRepo]]:
    settings = settings or get_settings()
    hf = HuggingFaceRegistryClient(settings)
    search_modified: dict[str, datetime | None] = {}

    async def _collect_hits(c: httpx.AsyncClient) -> None:
        for query in HF_DISCOVERY_QUERIES:
            hits = await hf.search_models_hits(query, limit=80, client=c)
            for hit in hits:
                prev = search_modified.get(hit.repo)
                merged = _merge_modified(prev, hit.last_modified)
                search_modified[hit.repo] = merged

    if client is not None:
        await _collect_hits(client)
    else:
        async with httpx.AsyncClient(timeout=max(settings.market_http_timeout_seconds, 30.0)) as c:
            await _collect_hits(c)

    candidates: list[tuple[str, datetime | None]] = []
    for repo, modified in search_modified.items():
        family = infer_albedo_model_family(repo)
        if family not in (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B):
            continue
        candidates.append((repo, modified))

    candidates.sort(
        key=lambda row: (
            0 if row[1] is not None else 1,
            -(row[1] or _EPOCH).timestamp(),
            row[0],
        )
    )

    models: list[HuggingFaceLatestRepo] = []
    fetch_cap = min(len(candidates), max(limit * 4, 40))

    async def _hydrate(c: httpx.AsyncClient) -> None:
        for repo, search_dt in candidates[:fetch_cap]:
            family = infer_albedo_model_family(repo)
            snap = await hf.fetch_model(repo, client=c)
            if snap is None:
                continue
            indexed_at = _merge_modified(search_dt, snap.created_at)
            models.append(
                HuggingFaceLatestRepo(
                    repo=repo,
                    model_family=family,
                    digest=snap.commit_sha,
                    indexed_at=indexed_at,
                    file_count=snap.file_count,
                    total_size_bytes=snap.total_bytes,
                    hub_url=huggingface_browse_url(repo, snap.revision),
                )
            )

    if client is not None:
        await _hydrate(client)
    else:
        async with httpx.AsyncClient(timeout=max(settings.market_http_timeout_seconds, 30.0)) as c:
            await _hydrate(c)

    models.sort(key=_repo_sort_key)
    capped = models[: max(limit, 1)]
    return len(candidates), capped
