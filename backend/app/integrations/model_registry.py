"""Unified remote model registry access (Hippius OCI + Hugging Face Hub)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import httpx

from app.config import Settings, get_settings
from app.integrations.hippius_registry import (
    HippiusRegistryClient,
    digests_match,
    normalize_digest,
)
from app.integrations.huggingface_registry import HuggingFaceRegistryClient

logger = logging.getLogger(__name__)

RepoHost = Literal["hippius", "huggingface"]


@dataclass(frozen=True)
class RemoteRepoFile:
    name: str
    digest: str
    size: int


@dataclass(frozen=True)
class RemoteRepoSnapshot:
    repo: str
    host: RepoHost
    revision: str
    remote_digest: str
    commit_message: str | None
    created_at: datetime | None
    files: tuple[RemoteRepoFile, ...]

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)


def infer_repo_host(digest: str | None) -> RepoHost:
    """Infer registry from on-chain digest format."""
    d = (digest or "").strip().lower()
    if d.startswith("revision:") or d.startswith("hf:"):
        return "huggingface"
    return "hippius"


def chain_revision(digest: str | None) -> str | None:
    if not digest:
        return None
    d = digest.strip()
    if d.startswith("revision:"):
        return d.split(":", 1)[1]
    if d.startswith("hf:"):
        return d.split(":", 1)[1]
    return None


def remote_digests_match(chain_digest: str | None, remote_digest: str | None) -> bool:
    if not chain_digest or not remote_digest:
        return False
    if digests_match(chain_digest, remote_digest):
        return True
    rev = chain_revision(chain_digest)
    if rev:
        remote = remote_digest.removeprefix("revision:").removeprefix("sha256:")
        return rev.lower() == remote.lower() or remote.lower().startswith(rev.lower())
    return False


class ModelRegistryClient:
    """Fetch model snapshots from Hippius or Hugging Face based on commit digest."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.hippius = HippiusRegistryClient(self.settings)
        self.huggingface = HuggingFaceRegistryClient(self.settings)

    async def fetch_snapshot(
        self,
        repo: str,
        chain_digest: str | None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> RemoteRepoSnapshot | None:
        primary = infer_repo_host(chain_digest)
        snapshot = await self._fetch_host(repo, chain_digest, primary, client)
        if snapshot is not None:
            return snapshot
        alternate: RepoHost = "huggingface" if primary == "hippius" else "hippius"
        return await self._fetch_host(repo, chain_digest, alternate, client)

    async def _fetch_host(
        self,
        repo: str,
        chain_digest: str | None,
        host: RepoHost,
        client: httpx.AsyncClient | None,
    ) -> RemoteRepoSnapshot | None:
        try:
            if host == "hippius":
                revision = self.settings.repo_track_revision
                manifest = await self.hippius.fetch_manifest(repo, revision, client=client)
                if manifest is None:
                    return None
                return RemoteRepoSnapshot(
                    repo=repo,
                    host="hippius",
                    revision=manifest.revision,
                    remote_digest=manifest.manifest_digest,
                    commit_message=manifest.commit_message,
                    created_at=manifest.created_at,
                    files=tuple(
                        RemoteRepoFile(name=f.name, digest=f.digest, size=f.size)
                        for f in manifest.files
                    ),
                )
            rev = chain_revision(chain_digest) or self.settings.repo_track_revision
            hf = await self.huggingface.fetch_revision(repo, rev, client=client)
            if hf is None:
                return None
            return RemoteRepoSnapshot(
                repo=repo,
                host="huggingface",
                revision=hf.revision,
                remote_digest=hf.commit_sha,
                commit_message=hf.commit_message,
                created_at=hf.created_at,
                files=tuple(
                    RemoteRepoFile(name=f.name, digest=f.digest, size=f.size) for f in hf.files
                ),
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise


def diff_remote_files(
    previous: tuple[RemoteRepoFile, ...] | None,
    current: tuple[RemoteRepoFile, ...],
) -> list[dict]:
    prev_map = {f.name: f for f in (previous or ())}
    curr_map = {f.name: f for f in current}
    changes: list[dict] = []
    for name, cur in curr_map.items():
        old = prev_map.get(name)
        if old is None:
            changes.append({"name": name, "change": "added", "digest": cur.digest, "size": cur.size})
        elif old.digest != cur.digest:
            changes.append(
                {
                    "name": name,
                    "change": "modified",
                    "digest": cur.digest,
                    "previous_digest": old.digest,
                    "size": cur.size,
                }
            )
    for name in prev_map:
        if name not in curr_map:
            changes.append({"name": name, "change": "removed", "digest": prev_map[name].digest})
    return changes
