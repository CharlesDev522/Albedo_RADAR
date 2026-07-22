"""Latest Albedo repos from Hugging Face Hub search."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

import httpx

from app.chain_reader.albedo_model_family import FAMILY_QWEN36_35B, FAMILY_QWEN3_4B, infer_albedo_model_family
from app.config import Settings, get_settings
from app.integrations.huggingface_registry import HuggingFaceRegistryClient, HuggingFaceSearchHit, hit_sort_value
from app.integrations.huggingface_search_config import HF_DISCOVERY_QUERIES, HF_SORT_CREATED_AT
from app.processing.repo_watch_targets import parse_hub_watch_hotkey
from app.schemas.repo_activity import HuggingFaceLatestRepo, RepoTrackEntry

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


def _merge_created(*values: datetime | None) -> datetime | None:
    valid = [v for v in values if v is not None]
    return max(valid) if valid else None


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
        }
    )


async def fetch_latest_huggingface_repos(
    *,
    limit: int = 10,
    sort: str = HF_SORT_CREATED_AT,
    tags: Sequence[str] | None = None,
    tracked_entries: Sequence[RepoTrackEntry] | None = None,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[int, list[HuggingFaceLatestRepo]]:
    settings = settings or get_settings()
    hf = HuggingFaceRegistryClient(settings)
    tag_list = [t.strip() for t in (tags or ()) if t.strip()]
    hit_by_repo: dict[str, HuggingFaceSearchHit] = {}

    async def _collect_hits(c: httpx.AsyncClient) -> None:
        for query in HF_DISCOVERY_QUERIES:
            hits = await hf.search_models_hits(
                query,
                limit=80,
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

    candidates: list[tuple[str, HuggingFaceSearchHit]] = []
    for repo, hit in hit_by_repo.items():
        family = infer_albedo_model_family(repo)
        if family not in (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B):
            continue
        candidates.append((repo, hit))

    candidates.sort(
        key=lambda row: (
            -hit_sort_value(row[1], sort),
            row[0],
        )
    )

    track_lookup = _hf_track_lookup(tracked_entries or ())
    models: list[HuggingFaceLatestRepo] = []
    fetch_cap = min(len(candidates), max(limit * 4, 40))

    async def _hydrate(c: httpx.AsyncClient) -> None:
        for repo, hit in candidates[:fetch_cap]:
            family = infer_albedo_model_family(repo)
            snap = await hf.fetch_model(repo, client=c)
            if snap is None:
                continue
            indexed_at = _indexed_at_for_sort(hit, sort)
            entry = HuggingFaceLatestRepo(
                repo=repo,
                model_family=family,
                digest=snap.commit_sha,
                indexed_at=indexed_at,
                file_count=snap.file_count,
                total_size_bytes=snap.total_bytes,
                hub_url=huggingface_browse_url(repo, snap.revision),
                downloads=hit.downloads,
                likes=hit.likes,
                tags=list(hit.tags),
            )
            models.append(_apply_track_status(entry, track_lookup.get(repo)))

    if client is not None:
        await _hydrate(client)
    else:
        async with httpx.AsyncClient(timeout=max(settings.market_http_timeout_seconds, 30.0)) as c:
            await _hydrate(c)

    models.sort(key=lambda repo: _repo_sort_key(repo, sort))
    capped = models[: max(limit, 1)]
    return len(candidates), capped
