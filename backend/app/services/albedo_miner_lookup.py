"""Miner identity lookup for enriching duel analysis with repo/coldkey."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CommitmentHistory, HotkeyRecord, Miner, MinerCommitment


@dataclass(frozen=True)
class MinerIdentity:
    coldkey: str | None
    repo: str | None
    uid: int | None
    commit_block: int | None = None


@dataclass
class MinerLookup:
    by_hotkey: dict[str, MinerIdentity]
    by_uid: dict[int, MinerIdentity]
    by_model_base: dict[str, MinerIdentity] = field(default_factory=dict)

    def resolve(
        self,
        *,
        hotkey: str | None = None,
        uid: int | None = None,
        model_uri: str | None = None,
        namespace: str | None = None,
        model_name: str | None = None,
    ) -> MinerIdentity | None:
        if hotkey and hotkey in self.by_hotkey:
            return self.by_hotkey[hotkey]
        if uid is not None and uid in self.by_uid:
            return self.by_uid[uid]
        base = model_uri_base(model_uri)
        if not base and namespace and model_name:
            base = f"{namespace}/{model_name}"
        if base and base in self.by_model_base:
            return self.by_model_base[base]
        return None

    @property
    def coverage_pct(self) -> float:
        if not self.by_hotkey:
            return 0.0
        with_repo = sum(1 for v in self.by_hotkey.values() if v.repo)
        return round(with_repo / len(self.by_hotkey) * 100, 1)


def model_uri_base(model_uri: str | None) -> str | None:
    if not model_uri:
        return None
    base = model_uri.split("@", 1)[0].strip()
    return base or None


def _identity_from_row(
    row: Any,
    *,
    repo: str | None = None,
    coldkey: str | None = None,
    uid: int | None = None,
    commit_block: int | None = None,
) -> MinerIdentity:
    return MinerIdentity(
        coldkey=coldkey if coldkey is not None else getattr(row, "coldkey", None),
        repo=repo if repo is not None else getattr(row, "repo", None),
        uid=uid if uid is not None else getattr(row, "uid", None),
        commit_block=commit_block if commit_block is not None else getattr(row, "commit_block", None),
    )


def _upsert_identity(
    target: dict[str, MinerIdentity],
    key: str,
    ident: MinerIdentity,
    *,
    overwrite: bool = False,
) -> None:
    if key not in target:
        target[key] = ident
        return
    if overwrite:
        target[key] = ident
        return
    existing = target[key]
    target[key] = MinerIdentity(
        coldkey=ident.coldkey or existing.coldkey,
        repo=ident.repo or existing.repo,
        uid=ident.uid if ident.uid is not None else existing.uid,
        commit_block=ident.commit_block or existing.commit_block,
    )


def _index_identity(
    lookup: MinerLookup,
    ident: MinerIdentity,
    *,
    hotkey: str | None,
    overwrite: bool = False,
) -> None:
    if hotkey:
        _upsert_identity(lookup.by_hotkey, hotkey, ident, overwrite=overwrite)
    if ident.uid is not None:
        if ident.uid not in lookup.by_uid:
            lookup.by_uid[ident.uid] = ident
        elif overwrite:
            lookup.by_uid[ident.uid] = ident
        else:
            existing = lookup.by_uid[ident.uid]
            lookup.by_uid[ident.uid] = MinerIdentity(
                coldkey=ident.coldkey or existing.coldkey,
                repo=ident.repo or existing.repo,
                uid=ident.uid,
                commit_block=ident.commit_block or existing.commit_block,
            )
    if ident.repo:
        _upsert_identity(lookup.by_model_base, ident.repo, ident, overwrite=overwrite)


def build_miner_lookup(commits: list) -> MinerLookup:
    lookup = MinerLookup(by_hotkey={}, by_uid={})
    for commit in commits:
        ident = _identity_from_row(commit)
        _index_identity(lookup, ident, hotkey=getattr(commit, "hotkey", None), overwrite=True)
    return lookup


def build_historical_miner_lookup(
    *,
    commitments: list[Any] | None = None,
    history: list[Any] | None = None,
    hotkey_records: list[Any] | None = None,
    miners: list[Any] | None = None,
) -> MinerLookup:
    """Merge current and historical chain identity for repo/coldkey crown history."""
    lookup = MinerLookup(by_hotkey={}, by_uid={})

    for row in history or []:
        ident = _identity_from_row(row)
        _index_identity(lookup, ident, hotkey=getattr(row, "hotkey", None), overwrite=False)
        base = model_uri_base(getattr(row, "model_uri", None))
        if base:
            _upsert_identity(lookup.by_model_base, base, ident, overwrite=False)

    for row in hotkey_records or []:
        ident = MinerIdentity(
            coldkey=getattr(row, "coldkey", None),
            repo=None,
            uid=getattr(row, "uid", None),
        )
        _index_identity(lookup, ident, hotkey=getattr(row, "hotkey", None), overwrite=False)

    for row in miners or []:
        ident = MinerIdentity(
            coldkey=getattr(row, "coldkey", None),
            repo=None,
            uid=getattr(row, "uid", None),
        )
        _index_identity(lookup, ident, hotkey=getattr(row, "hotkey", None), overwrite=False)

    for commit in commitments or []:
        ident = _identity_from_row(commit)
        hotkey = getattr(commit, "hotkey", None)
        _index_identity(lookup, ident, hotkey=hotkey, overwrite=True)
        base = model_uri_base(getattr(commit, "model_uri", None))
        if base:
            _upsert_identity(lookup.by_model_base, base, ident, overwrite=True)

    return lookup


async def load_historical_miner_lookup(db: AsyncSession, subnet: int) -> MinerLookup:
    from app.chain_reader.subnet_commit_rules import model_versions_sql_tuple

    versions = model_versions_sql_tuple(subnet)
    commitments = (
        await db.execute(
            select(MinerCommitment).where(
                MinerCommitment.subnet == subnet,
                MinerCommitment.version.in_(versions),
            )
        )
    ).scalars().all()
    history = (
        await db.execute(select(CommitmentHistory).where(CommitmentHistory.subnet == subnet))
    ).scalars().all()
    hotkey_records = (
        await db.execute(select(HotkeyRecord).where(HotkeyRecord.subnet == subnet))
    ).scalars().all()
    miners = (await db.execute(select(Miner).where(Miner.subnet == subnet))).scalars().all()
    return build_historical_miner_lookup(
        commitments=list(commitments),
        history=list(history),
        hotkey_records=list(hotkey_records),
        miners=list(miners),
    )


def build_coldkey_repos_map(lookup: MinerLookup | None) -> dict[str, list[str]]:
    """Map coldkey → Hippius repos (clusters-style, from commitment registry)."""
    if not lookup:
        return {}
    grouped: dict[str, set[str]] = defaultdict(set)
    for ident in lookup.by_hotkey.values():
        if ident.coldkey and ident.repo:
            grouped[ident.coldkey].add(ident.repo)
    return {ck: sorted(repos) for ck, repos in grouped.items()}


def build_repo_coldkeys_map(lookup: MinerLookup | None) -> dict[str, list[str]]:
    """Map repo → coldkeys operating that repo."""
    if not lookup:
        return {}
    grouped: dict[str, set[str]] = defaultdict(set)
    for ident in lookup.by_hotkey.values():
        if ident.coldkey and ident.repo:
            grouped[ident.repo].add(ident.coldkey)
    return {repo: sorted(cks) for repo, cks in grouped.items()}


def short_coldkey(coldkey: str, n: int = 8) -> str:
    return coldkey if len(coldkey) <= n + 2 else f"{coldkey[:n]}…"


def repo_entity_label(repo: str, coldkeys: list[str] | None = None) -> str:
    cks = coldkeys or []
    if len(cks) == 1:
        return f"{repo} ({short_coldkey(cks[0])})"
    if len(cks) > 1:
        return f"{repo} ({len(cks)} coldkeys)"
    return repo


def coldkey_entity_label(coldkey: str, repos: list[str] | None = None) -> str:
    linked = repos or []
    if len(linked) == 1:
        return f"{linked[0]} ({short_coldkey(coldkey)})"
    if len(linked) > 1:
        return f"{linked[0]} +{len(linked) - 1} ({short_coldkey(coldkey)})"
    return short_coldkey(coldkey, 12)
