"""Discover repos for priority Albedo miner namespaces (dual Hippius + HF watch)."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import httpx

from app.chain_reader.albedo_model_family import (
    FAMILY_QWEN36_35B,
    FAMILY_QWEN3_4B,
    infer_albedo_model_family,
)
from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard
from app.integrations.hippius_hub_client import HippiusHubClient, HippiusHubModel
from app.integrations.huggingface_registry import HuggingFaceRegistryClient
from app.integrations.model_registry import RepoHost

logger = logging.getLogger(__name__)

_URI_RE = re.compile(r"^([^@]+)@")


@dataclass(frozen=True)
class ChallengerStats:
    duels: int = 0
    wins: int = 0
    coronations: int = 0

    @property
    def win_pct(self) -> float:
        return round(self.wins / self.duels * 100, 1) if self.duels else 0.0


@dataclass(frozen=True)
class WatchNamespace:
    namespace: str
    source: str  # pinned | top_challenger
    rank: int | None = None
    stats: ChallengerStats | None = None


def _repo_from_model_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    m = _URI_RE.match(uri.strip())
    if not m:
        return None
    repo = m.group(1)
    if repo.startswith("registry.hippius.com/"):
        repo = repo.split("/", 1)[1]
    return repo if "/" in repo else None


def _namespace_from_repo(repo: str) -> str | None:
    if "/" not in repo:
        return None
    return repo.split("/", 1)[0].lower()


def _namespace_matches(repo: str, namespaces: set[str]) -> bool:
    ns = _namespace_from_repo(repo)
    return bool(ns and ns in namespaces)


def compute_challenger_stats(
    dashboard: dict[str, Any],
) -> tuple[dict[str, ChallengerStats], dict[str, ChallengerStats]]:
    """Aggregate challenger duels by namespace and repo from eval_runs."""
    ns_stats: dict[str, ChallengerStats] = defaultdict(ChallengerStats)
    repo_stats: dict[str, ChallengerStats] = defaultdict(ChallengerStats)

    for run in dashboard.get("eval_runs") or []:
        if not isinstance(run, dict):
            continue
        repo = _repo_from_model_uri(run.get("model_uri"))
        if not repo:
            continue
        family = infer_albedo_model_family(repo)
        if family not in (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B):
            continue
        ns = _namespace_from_repo(repo)
        if not ns:
            continue
        won = bool(run.get("challenger_won"))
        coronated = bool(run.get("coronated"))
        for bucket, key in ((ns_stats, ns), (repo_stats, repo)):
            current = bucket[key]
            bucket[key] = ChallengerStats(
                duels=current.duels + 1,
                wins=current.wins + (1 if won else 0),
                coronations=current.coronations + (1 if coronated else 0),
            )
    return dict(ns_stats), dict(repo_stats)


def resolve_watch_namespaces(
    settings: Settings,
    dashboard: dict[str, Any] | None = None,
) -> list[WatchNamespace]:
    """Pinned namespaces plus top challengers from duel analysis."""
    pinned = [ns.strip().lower() for ns in (settings.priority_miner_namespaces or []) if ns.strip()]
    pinned_set = set(pinned)
    result: list[WatchNamespace] = [
        WatchNamespace(namespace=ns, source="pinned", rank=None) for ns in pinned
    ]

    if not dashboard:
        return result

    ns_stats, _repo_stats = compute_challenger_stats(dashboard)
    ranked = sorted(
        ns_stats.items(),
        key=lambda item: (-item[1].duels, -item[1].wins, -item[1].coronations, item[0]),
    )
    top_n = max(settings.priority_challenger_top_n, 0)
    rank = 1
    for ns, stats in ranked:
        if ns in pinned_set:
            continue
        if stats.duels < 2:
            continue
        if rank > top_n:
            break
        result.append(
            WatchNamespace(namespace=ns, source="top_challenger", rank=rank, stats=stats)
        )
        rank += 1
    return result


def _repos_from_dashboard(dashboard: dict[str, Any], namespaces: set[str]) -> set[str]:
    repos: set[str] = set()
    for run in dashboard.get("eval_runs") or []:
        if not isinstance(run, dict):
            continue
        repo = _repo_from_model_uri(run.get("model_uri"))
        if repo and _namespace_matches(repo, namespaces):
            repos.add(repo)
        king = run.get("king") or {}
        if isinstance(king, dict):
            repo = _repo_from_model_uri(king.get("model_uri"))
            if repo and _namespace_matches(repo, namespaces):
                repos.add(repo)
    reign = dashboard.get("reign") or {}
    for member in reign.get("members") or []:
        if not isinstance(member, dict):
            continue
        repo = _repo_from_model_uri(member.get("model_uri"))
        if not repo:
            ns = member.get("namespace")
            name = member.get("model_name")
            if ns and name:
                repo = f"{ns}/{name}"
        if repo and _namespace_matches(repo, namespaces):
            repos.add(repo)
    return repos


def hippius_browse_url(repo: str, revision: str = "main") -> str:
    return f"https://hub.hippius.com/models/{repo}/{revision}"


def huggingface_browse_url(repo: str, revision: str = "main") -> str:
    return f"https://huggingface.co/{repo}/tree/{revision}"


def _repos_from_hippius_hub(
    hub_index: dict[str, HippiusHubModel],
    namespaces: set[str],
) -> set[str]:
    repos: set[str] = set()
    for repo in hub_index:
        if not _namespace_matches(repo, namespaces):
            continue
        family = infer_albedo_model_family(repo)
        if family in (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B):
            repos.add(repo)
    return repos


async def discover_priority_miner_repos(
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    dashboard: dict[str, Any] | None = None,
    hub_index: dict[str, HippiusHubModel] | None = None,
) -> list[str]:
    """Collect Albedo repos for pinned + top-challenger namespaces."""
    settings = settings or get_settings()
    dashboard_payload = dashboard
    if dashboard_payload is None:
        try:
            dashboard_payload = await fetch_dashboard(settings=settings)
        except Exception:
            dashboard_payload = {}

    watch = resolve_watch_namespaces(settings, dashboard_payload)
    namespaces = {w.namespace for w in watch}
    if not namespaces:
        return []

    repos: set[str] = set()
    if dashboard_payload:
        repos |= _repos_from_dashboard(dashboard_payload, namespaces)

    hub = HippiusHubClient(settings)
    index = hub_index
    if index is None:
        try:
            index = await hub.fetch_albedo_index(client=client)
        except Exception:
            logger.warning("priority miner Hippius hub discovery failed", exc_info=True)
            index = {}
    if index:
        repos |= _repos_from_hippius_hub(index, namespaces)

    hf = HuggingFaceRegistryClient(settings)
    for ns in sorted(namespaces):
        try:
            author_models = await hf.list_author_models(ns, client=client)
            for repo in author_models:
                family = infer_albedo_model_family(repo)
                if family in (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B):
                    repos.add(repo)
        except Exception:
            logger.warning("priority miner HF author discovery failed ns=%s", ns, exc_info=True)
        for query in (f"{ns}/albedo-qwen3.6-35b", f"{ns}/albedo-qwen3-4b"):
            try:
                found = await hf.search_models(query, limit=50, client=client)
                for repo in found:
                    if repo.lower().startswith(f"{ns}/"):
                        repos.add(repo)
            except Exception:
                logger.warning("priority miner HF search failed q=%s", query, exc_info=True)

    return sorted(repos)


def priority_hosts() -> tuple[RepoHost, RepoHost]:
    return ("hippius", "huggingface")
