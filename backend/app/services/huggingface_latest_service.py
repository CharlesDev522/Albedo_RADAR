"""Latest Albedo repos from Hugging Face Hub search."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

import httpx

from app.chain_reader.albedo_model_family import FAMILY_QWEN36_35B, FAMILY_QWEN3_4B, infer_albedo_model_family
from app.config import Settings, get_settings
from app.integrations.huggingface_registry import HuggingFaceRegistryClient, HuggingFaceSearchHit, hit_sort_value
from app.integrations.huggingface_search_config import (
    HF_DISCOVERY_QUERIES,
    HF_LATEST_CACHE_TTL_SECONDS,
    HF_SEARCH_LIMIT_PER_QUERY,
    HF_SORT_CREATED_AT,
)
from app.processing.repo_watch_targets import parse_hub_watch_hotkey
from app.schemas.repo_activity import HuggingFaceLatestRepo, RepoTrackEntry
from app.services.hf_latest_cache import cache_get, cache_peek, cache_set

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def huggingface_browse_url(repo: str, revision: str | None = None) -> str:
    if revision:
        rev = revision.removeprefix("revision:").removeprefix("hf:")
        return f"https://huggingface.co/{repo}/tree/{rev}"
    return f"https://huggingface.co/{repo}"


def huggingface_search_url(
    *,
    query: str = HF_DISCOVERY_QUERIES[0],
    sort: str = HF_SORT_CREATED_AT,
    tags: Sequence[str] | None = None,
) -> str:
    params = [f"search={query}", f"sort={sort}", "direction=-1"]
    for tag in tags or ():
        if tag.strip():
            params.append(f"filter={tag.strip()}")
    return f"https://huggingface.co/models?{'&'.join(params)}"


def _cache_key(*, limit: int, sort: str, tags: Sequence[str] | None) -> str:
    tag_key = ",".join(sorted(t.strip().lower() for t in (tags or ()) if t.strip()))
    return f"hf-latest:{sort}:{tag_key}:{limit}"


def _repo_sort_key(repo: HuggingFaceLatestRepo, sort: str) -> tuple[int, float, str]:
    if sort in ("downloads", "likes"):
        metric = repo.downloads if sort == "downloads" else repo.likes
        return (0 if metric > 0 else 1, -float(metric), repo.repo)
    if repo.indexed_at is None:
        return (1, 0.0, repo.repo)
    return (0, -repo.indexed_at.timestamp(), repo.repo)


def _indexed_at_for_sort(hit: HuggingFaceSearchHit, sort: str) -> datetime | None:
    if sort == "lastModified":
        return hit.last_modified or hit.created_at
    return hit.created_at


def _is_hf_track(track: RepoTrackEntry) -> bool:
    if track.repo_host == "huggingface":
        return True
    if track.track_source != "hub_watch":
        return False
    _repo, host = parse_hub_watch_hotkey(track.hotkey)
    return host in (None, "huggingface")


def _hf_track_lookup(tracks: Sequence[RepoTrackEntry]) -> dict[str, RepoTrackEntry]:
    by_repo: dict[str, RepoTrackEntry] = {}
    for track in tracks:
        if not _is_hf_track(track):
            continue
        existing = by_repo.get(track.repo)
        if existing is None:
            by_repo[track.repo] = track
            continue
        existing_ts = existing.last_checked_at or existing.last_updated
        track_ts = track.last_checked_at or track.last_updated
        if track_ts and (existing_ts is None or track_ts > existing_ts):
            by_repo[track.repo] = track
    return by_repo


def _apply_track_status(
    repo: HuggingFaceLatestRepo,
    track: RepoTrackEntry | None,
) -> HuggingFaceLatestRepo:
    if track is None:
        return repo
    return repo.model_copy(
        update={
            "is_tracked": True,
            "digest_in_sync": track.digest_in_sync,
            "pending_hub_poll": track.pending_hub_poll,
            "tracked_uid": track.uid,
            "track_source": track.track_source,
            "digest": track.hub_digest or repo.digest,
            "file_count": track.file_count if track.file_count is not None else repo.file_count,
            "total_size_bytes": track.total_bytes if track.total_bytes is not None else repo.total_size_bytes,
            "hub_url": huggingface_browse_url(
                repo.repo,
                track.hub_revision if track.hub_revision and track.hub_revision != "main" else None,
            ),
        }
    )


def _repo_from_hit(
    repo: str,
    hit: HuggingFaceSearchHit,
    *,
    sort: str,
    track: RepoTrackEntry | None,
) -> HuggingFaceLatestRepo:
    family = infer_albedo_model_family(repo)
    entry = HuggingFaceLatestRepo(
        repo=repo,
        model_family=family,
        digest="",
        indexed_at=_indexed_at_for_sort(hit, sort),
        file_count=None,
        total_size_bytes=None,
        hub_url=huggingface_browse_url(repo),
        downloads=hit.downloads,
        likes=hit.likes,
        tags=list(hit.tags),
    )
    return _apply_track_status(entry, track)


async def _fetch_latest_huggingface_repos_uncached(
    *,
    limit: int,
    sort: str,
    tags: Sequence[str] | None,
    tracked_entries: Sequence[RepoTrackEntry] | None,
    settings: Settings,
    client: httpx.AsyncClient | None,
) -> tuple[int, list[HuggingFaceLatestRepo]]:
    hf = HuggingFaceRegistryClient(settings)
    tag_list = [t.strip() for t in (tags or ()) if t.strip()]
    hit_by_repo: dict[str, HuggingFaceSearchHit] = {}
    search_limit = max(limit * 2, HF_SEARCH_LIMIT_PER_QUERY)

    async def _collect_hits(c: httpx.AsyncClient) -> None:
        for query in HF_DISCOVERY_QUERIES:
            hits = await hf.search_models_hits(
                query,
                limit=search_limit,
                sort=sort,
                direction=-1,
                tags=tag_list or None,
                client=c,
            )
            for hit in hits:
                prev = hit_by_repo.get(hit.repo)
                if prev is None or hit_sort_value(hit, sort) > hit_sort_value(prev, sort):
                    hit_by_repo[hit.repo] = hit

    if client is not None:
        await _collect_hits(client)
    else:
        async with httpx.AsyncClient(timeout=max(settings.market_http_timeout_seconds, 30.0)) as c:
            await _collect_hits(c)

    track_lookup = _hf_track_lookup(tracked_entries or ())
    models: list[HuggingFaceLatestRepo] = []
    for repo, hit in hit_by_repo.items():
        family = infer_albedo_model_family(repo)
        if family not in (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B):
            continue
        models.append(_repo_from_hit(repo, hit, sort=sort, track=track_lookup.get(repo)))

    models.sort(key=lambda repo: _repo_sort_key(repo, sort))
    capped = models[: max(limit, 1)]
    return len(models), capped


async def fetch_latest_huggingface_repos(
    *,
    limit: int = 10,
    sort: str = HF_SORT_CREATED_AT,
    tags: Sequence[str] | None = None,
    tracked_entries: Sequence[RepoTrackEntry] | None = None,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    force_refresh: bool = False,
) -> tuple[int, list[HuggingFaceLatestRepo]]:
    settings = settings or get_settings()
    key = _cache_key(limit=limit, sort=sort, tags=tags)

    if not force_refresh:
        cached = cache_get(key, ttl_seconds=HF_LATEST_CACHE_TTL_SECONDS)
        if cached is not None:
            total, repos = cached
            if tracked_entries:
                track_lookup = _hf_track_lookup(tracked_entries)
                repos = [
                    _apply_track_status(repo, track_lookup.get(repo.repo))
                    for repo in repos
                ]
            return total, repos

    try:
        result = await _fetch_latest_huggingface_repos_uncached(
            limit=limit,
            sort=sort,
            tags=tags,
            tracked_entries=tracked_entries,
            settings=settings,
            client=client,
        )
        cache_set(key, (result[0], [repo.model_copy() for repo in result[1]]))
        return result
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            stale = cache_peek(key)
            if stale is not None:
                total, repos = stale  # type: ignore[misc]
                if tracked_entries:
                    track_lookup = _hf_track_lookup(tracked_entries)
                    repos = [
                        _apply_track_status(repo, track_lookup.get(repo.repo))
                        for repo in repos
                    ]
                return total, repos
        raise


async def discover_huggingface_repos(
    hf: HuggingFaceRegistryClient,
    client: httpx.AsyncClient,
    *,
    limit_per_query: int = HF_SEARCH_LIMIT_PER_QUERY,
) -> list[str]:
    """Low-volume HF discovery for registry sync (cached search hits only)."""
    key = f"hf-discovery:{limit_per_query}"
    cached = cache_get(key, ttl_seconds=HF_LATEST_CACHE_TTL_SECONDS)
    if cached is not None:
        return list(cached)

    repos: list[str] = []
    for query in HF_DISCOVERY_QUERIES:
        hits = await hf.search_models_hits(
            query,
            limit=limit_per_query,
            sort=HF_SORT_CREATED_AT,
            direction=-1,
            client=client,
        )
        repos.extend(hit.repo for hit in hits)
    deduped = list(dict.fromkeys(repos))
    cache_set(key, deduped)
    return deduped
