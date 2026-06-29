"""Read-only Hippius OCI registry client (anonymous public pulls)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

OCI_MANIFEST_ACCEPT = "application/vnd.oci.image.manifest.v1+json"


@dataclass(frozen=True)
class HippiusManifestFile:
    name: str
    digest: str
    size: int


@dataclass(frozen=True)
class HippiusManifest:
    repo: str
    revision: str
    manifest_digest: str
    commit_message: str | None
    created_at: datetime | None
    files: tuple[HippiusManifestFile, ...]

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)


def normalize_digest(digest: str | None) -> str | None:
    if not digest:
        return None
    d = digest.strip()
    if d.startswith("sha256:"):
        return d
    if len(d) == 64 and all(c in "0123456789abcdef" for c in d.lower()):
        return f"sha256:{d}"
    return d


def digests_match(a: str | None, b: str | None) -> bool:
    na = normalize_digest(a)
    nb = normalize_digest(b)
    return bool(na and nb and na.lower() == nb.lower())


class HippiusRegistryClient:
    """Fetch tags and manifests from registry.hippius.com via Harbor token flow."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.hippius_registry_url.rstrip("/")

    async def list_tags(self, repo: str, client: httpx.AsyncClient | None = None) -> list[str]:
        token = await self._pull_token(repo, client)
        url = f"{self.base_url}/v2/{repo}/tags/list"
        resp = await self._request("GET", url, token, client=client)
        data = resp.json()
        tags = data.get("tags") or []
        return sorted(tags)

    async def fetch_manifest(
        self,
        repo: str,
        revision: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> HippiusManifest | None:
        revision = revision or self.settings.repo_track_revision
        token = await self._pull_token(repo, client)
        url = f"{self.base_url}/v2/{repo}/manifests/{revision}"
        resp = await self._request(
            "GET",
            url,
            token,
            headers={"Accept": OCI_MANIFEST_ACCEPT},
            client=client,
        )
        manifest_digest = normalize_digest(resp.headers.get("docker-content-digest"))
        if not manifest_digest:
            logger.warning("no docker-content-digest for %s@%s", repo, revision)
            return None
        payload = resp.json()
        return _parse_manifest(repo, revision, manifest_digest, payload)

    async def _pull_token(self, repo: str, client: httpx.AsyncClient | None) -> str:
        scope = f"repository:{repo}:pull"
        url = f"{self.base_url}/service/token"
        params = {"service": "harbor-registry", "scope": scope}
        resp = await self._request("GET", url, token=None, params=params, client=client)
        data = resp.json()
        token = data.get("token")
        if not token:
            raise RuntimeError(f"no bearer token for {repo}")
        return token

    async def _request(
        self,
        method: str,
        url: str,
        token: str | None,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> httpx.Response:
        hdrs = dict(headers or {})
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        timeout = self.settings.market_http_timeout_seconds

        async def _do(c: httpx.AsyncClient) -> httpx.Response:
            resp = await c.request(method, url, headers=hdrs, params=params)
            resp.raise_for_status()
            return resp

        if client is not None:
            return await _do(client)
        async with httpx.AsyncClient(timeout=timeout) as c:
            return await _do(c)


def _parse_manifest(
    repo: str,
    revision: str,
    manifest_digest: str,
    payload: dict[str, Any],
) -> HippiusManifest:
    annotations = payload.get("annotations") or {}
    commit_message = annotations.get("org.hippius.commit.message")
    created_raw = annotations.get("org.opencontainers.image.created")
    created_at: datetime | None = None
    if created_raw:
        try:
            created_at = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
        except ValueError:
            created_at = None

    files: list[HippiusManifestFile] = []
    for layer in payload.get("layers") or []:
        layer_ann = layer.get("annotations") or {}
        name = layer_ann.get("org.opencontainers.image.title") or layer.get("digest", "unknown")
        digest = normalize_digest(layer.get("digest")) or ""
        size = int(layer.get("size") or 0)
        files.append(HippiusManifestFile(name=name, digest=digest, size=size))

    files.sort(key=lambda f: f.name)
    return HippiusManifest(
        repo=repo,
        revision=revision,
        manifest_digest=manifest_digest,
        commit_message=commit_message,
        created_at=created_at,
        files=tuple(files),
    )


def diff_manifest_files(
    previous: tuple[HippiusManifestFile, ...] | None,
    current: tuple[HippiusManifestFile, ...],
) -> list[dict[str, Any]]:
    """Return added/changed/removed files between two manifests."""
    prev_map = {f.name: f for f in (previous or ())}
    curr_map = {f.name: f for f in current}
    changes: list[dict[str, Any]] = []

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
