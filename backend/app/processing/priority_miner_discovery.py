"""Discover repos for priority Albedo miner namespaces (dual Hippius + HF watch)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.chain_reader.albedo_model_family import (
    FAMILY_QWEN36_35B,
    FAMILY_QWEN3_4B,
    infer_albedo_model_family,
)
from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard
from app.integrations.huggingface_registry import HuggingFaceRegistryClient
from app.integrations.model_registry import RepoHost

logger = logging.getLogger(__name__)

_URI_RE = re.compile(r"^([^@]+)@")


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


def _namespace_matches(repo: str, namespaces: set[str]) -> bool:
    if "/" not in repo:
        return False
    ns = repo.split("/", 1)[0].lower()
    return ns in namespaces


def _repos_from_dashboard(dashboard: dict[str, Any], namespaces: set[str]) -> set[str]:
    repos: set[str] = set()
    for run in dashboard.get("eval_runs") or []:
        if not isinstance(run, dict):
            continue
        for key in ("model_uri",):
            repo = _repo_from_model_uri(run.get(key))
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


async def discover_priority_miner_repos(
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    """Collect Albedo repos for configured priority miner namespaces."""
    settings = settings or get_settings()
    raw_namespaces = settings.priority_miner_namespaces or []
    namespaces = {ns.strip().lower() for ns in raw_namespaces if ns.strip()}
    if not namespaces:
        return []

    repos: set[str] = set()

    try:
        dashboard = await fetch_dashboard(settings=settings)
        repos |= _repos_from_dashboard(dashboard, namespaces)
    except Exception:
        logger.warning("priority miner dashboard discovery failed", exc_info=True)

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
