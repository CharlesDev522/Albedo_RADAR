"""Miner identity lookup for enriching duel analysis with repo/coldkey."""

from __future__ import annotations

from dataclasses import dataclass


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

    def resolve(self, *, hotkey: str | None = None, uid: int | None = None) -> MinerIdentity | None:
        if hotkey and hotkey in self.by_hotkey:
            return self.by_hotkey[hotkey]
        if uid is not None and uid in self.by_uid:
            return self.by_uid[uid]
        return None

    @property
    def coverage_pct(self) -> float:
        if not self.by_hotkey:
            return 0.0
        with_repo = sum(1 for v in self.by_hotkey.values() if v.repo)
        return round(with_repo / len(self.by_hotkey) * 100, 1)


def build_miner_lookup(commits: list) -> MinerLookup:
    by_hotkey: dict[str, MinerIdentity] = {}
    by_uid: dict[int, MinerIdentity] = {}
    for commit in commits:
        ident = MinerIdentity(
            coldkey=getattr(commit, "coldkey", None),
            repo=getattr(commit, "repo", None),
            uid=getattr(commit, "uid", None),
            commit_block=getattr(commit, "commit_block", None),
        )
        hotkey = getattr(commit, "hotkey", None)
        if hotkey:
            by_hotkey[hotkey] = ident
        if ident.uid is not None:
            by_uid[ident.uid] = ident
    return MinerLookup(by_hotkey=by_hotkey, by_uid=by_uid)
