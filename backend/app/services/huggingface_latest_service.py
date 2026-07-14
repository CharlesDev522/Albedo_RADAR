"""Latest Albedo repos from Hugging Face Hub search."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.chain_reader.albedo_model_family import FAMILY_QWEN36_35B, FAMILY_QWEN3_4B, infer_albedo_model_family
from app.config import Settings, get_settings
from app.integrations.huggingface_registry import HuggingFaceRegistryClient
from app.schemas.repo_activity import HuggingFaceLatestRepo

HF_DISCOVERY_QUERIES = ("albedo-qwen3.6-35b", "albedo-qwen3-4b")


def huggingface_browse_url(repo: str, revision: str | None = None) -> str:
    if revision:
        rev = revision.removeprefix("revision:").removeprefix("hf:")
        return f"https://huggingface.co/{repo}/tree/{rev}"
    return f"https://huggingface.co/{repo}"


async def fetch_latest_huggingface_repos(
    *,
    limit: int = 10,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[int, list[HuggingFaceLatestRepo]]:
    settings = settings or get_settings()
    hf = HuggingFaceRegistryClient(settings)
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    seen: set[str] = set()
    models: list[HuggingFaceLatestRepo] = []

    async def _search(c: httpx.AsyncClient) -> None:
        for query in HF_DISCOVERY_QUERIES:
            repos = await hf.search_models(query, limit=50, client=c)
            for repo in repos:
                if repo in seen:
                    continue
                family = infer_albedo_model_family(repo)
                if family not in (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B):
                    continue
                snap = await hf.fetch_model(repo, client=c)
                if snap is None:
                    continue
                seen.add(repo)
                models.append(
                    HuggingFaceLatestRepo(
                        repo=repo,
                        model_family=family,
                        digest=snap.commit_sha,
                        indexed_at=snap.created_at,
                        file_count=snap.file_count,
                        total_size_bytes=snap.total_bytes,
                        hub_url=huggingface_browse_url(repo, snap.revision),
                    )
                )

    if client is not None:
        await _search(client)
    else:
        async with httpx.AsyncClient(timeout=max(settings.market_http_timeout_seconds, 30.0)) as c:
            await _search(c)

    models.sort(key=lambda m: m.indexed_at or epoch, reverse=True)
    capped = models[: max(limit, 1)]
    return len(models), capped
