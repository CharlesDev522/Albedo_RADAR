"""Kind-specific alert titles, messages, and display formatting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.chain_reader.commitment_scanner import Commit
from app.chain_reader.slot_commitment_scanner import SlotStatus
from app.notifications.formatters import commit_alert_detail, repo_alert_detail, slot_alert_detail
from app.notifications.kinds import AlertKind

KIND_LABELS: dict[AlertKind, str] = {
    "crown_won": "King Coronated",
    "crown_lost": "King Dethroned",
    "duel_new": "Albedo Eval Started",
    "king_defended": "King Defended",
    "slot_new": "UID Published Commitment",
    "slot_changed": "UID Published Commitment",
    "commit_new": "CommitmentOf Revealed",
    "commit_updated": "CommitmentOf Changed",
    "repo_new": "New Hippius Repo",
    "repo_updated": "Hippius Manifest Updated",
    "reg_fee_low": "Registration Burn Low",
    "eval_dq": "Eval DQ (Disqualified)",
}

# Ordered keys per kind for Slack detail lines (most important first).
DETAIL_ORDER: dict[AlertKind, tuple[str, ...]] = {
    "crown_won": (
        "repo",
        "namespace",
        "uid",
        "hotkey",
        "king_version",
        "defeated_king_version",
        "win_margin",
        "model_uri",
        "finished_at",
        "eval_run_id",
    ),
    "crown_lost": (
        "previous_king_version",
        "new_king_version",
        "previous_model_uri",
        "new_model_uri",
        "new_repo",
    ),
    "duel_new": (
        "eval_run_id",
        "repo",
        "namespace",
        "uid",
        "hotkey",
        "model_uri",
        "state",
        "king_version",
        "king_repo",
    ),
    "king_defended": (
        "eval_run_id",
        "repo",
        "namespace",
        "uid",
        "hotkey",
        "king_version",
        "king_repo",
        "score_challenger",
        "score_king",
        "win_margin",
        "finished_at",
    ),
    "commit_new": ("repo", "uid", "hotkey", "digest", "model_uri", "commit_block", "version"),
    "commit_updated": (
        "repo",
        "uid",
        "hotkey",
        "digest",
        "previous_payload_hash",
        "commit_block",
        "model_uri",
    ),
    "slot_new": ("uid", "hotkey", "commitment_type", "commit_block", "detail"),
    "slot_changed": ("uid", "hotkey", "commitment_type", "commit_block", "detail", "previous"),
    "repo_new": ("repo", "model_family", "hub_digest", "revision", "uid", "hotkey"),
    "repo_updated": (
        "repo",
        "hub_digest",
        "previous_digest",
        "revision",
        "commit_message",
        "uid",
        "hotkey",
    ),
    "reg_fee_low": (
        "registration_burn_tao",
        "threshold_tao",
        "alpha_price_tao",
        "chain_block",
        "network",
    ),
    "eval_dq": (
        "uid",
        "hotkey",
        "repo",
        "fault_class",
        "fault_code",
        "fault_message",
        "submission_id",
        "eval_run_id",
        "state",
        "updated_at",
        "model_uri",
    ),
}


@dataclass(frozen=True)
class AlertContent:
    kind: AlertKind
    title: str
    message: str
    source_key: str
    detail: dict[str, Any]
    subnet: int | None = None
    severity: str | None = None


def _short_digest(digest: str | None, n: int = 12) -> str:
    if not digest:
        return "?"
    d = str(digest)
    return d if len(d) <= n else f"{d[:n]}…"


def build_commit_new_alert(commit: Commit) -> AlertContent:
    repo = commit.commit_payload.get("repo", "?")
    version = commit.commit_payload.get("version", "pipe")
    detail = commit_alert_detail(commit)
    return AlertContent(
        kind="commit_new",
        title=f"[commit_new] uid {commit.uid} revealed {version} — {repo}",
        message=(
            f"SN{commit.netuid} uid {commit.uid} revealed CommitmentOf ({version} pipe) "
            f"at block {commit.block_number} | {_short_digest(commit.commit_payload.get('digest'))}"
        ),
        source_key=f"commit_new:{commit.netuid}:{commit.hotkey}:{commit.payload_hash}",
        detail=detail,
        subnet=commit.netuid,
    )


def build_commit_updated_alert(commit: Commit, *, previous_hash: str) -> AlertContent:
    repo = commit.commit_payload.get("repo", "?")
    detail = commit_alert_detail(commit, previous_hash=previous_hash)
    return AlertContent(
        kind="commit_updated",
        title=f"[commit_updated] uid {commit.uid} changed CommitmentOf — {repo}",
        message=(
            f"SN{commit.netuid} uid {commit.uid} changed revealed model at block {commit.block_number} "
            f"| digest {_short_digest(previous_hash)} → {_short_digest(commit.commit_payload.get('digest'))}"
        ),
        source_key=f"commit_updated:{commit.netuid}:{commit.hotkey}:{commit.payload_hash}",
        detail=detail,
        subnet=commit.netuid,
    )


def build_slot_new_alert(slot: SlotStatus, netuid: int) -> AlertContent:
    detail = slot_alert_detail(slot)
    model = slot.detail or "?"
    pipe = slot.commitment_type.value
    return AlertContent(
        kind="slot_new",
        title=f"[slot_new] uid {slot.uid} published {pipe} commitment",
        message=(
            f"SN{netuid} uid {slot.uid} went from no commitment to {pipe} pipe "
            f"at block {slot.commit_block} · {model}"
        ),
        source_key=f"slot_new:{netuid}:{slot.uid}:{slot.payload_hash or slot.commit_block}",
        detail=detail,
        subnet=netuid,
    )


def build_slot_changed_alert(
    slot: SlotStatus,
    netuid: int,
    *,
    previous: dict[str, Any],
) -> AlertContent:
    detail = slot_alert_detail(slot, previous=previous)
    model = slot.detail or "?"
    pipe = slot.commitment_type.value
    prev_type = previous.get("commitment_type") or "none"
    prev_detail = previous.get("detail") or "none"
    return AlertContent(
        kind="slot_changed",
        title=f"[slot_changed] uid {slot.uid} published {pipe} commitment",
        message=(
            f"SN{netuid} uid {slot.uid} published {pipe} commitment at block {slot.commit_block} "
            f"(was {prev_type}: {prev_detail}) · {model}"
        ),
        source_key=f"slot_changed:{netuid}:{slot.uid}:{slot.payload_hash or slot.commit_block}",
        detail=detail,
        subnet=netuid,
    )


def build_repo_new_alert(
    *,
    netuid: int,
    repo: str,
    event_type: str,
    source_key: str,
    uid: int | None = None,
    hotkey: str | None = None,
    coldkey: str | None = None,
    model_family: str | None = None,
    hub_digest: str | None = None,
    revision: str | None = None,
    commit_message: str | None = None,
    meta: dict[str, Any] | None = None,
) -> AlertContent:
    detail = repo_alert_detail(
        repo=repo,
        event_type=event_type,
        uid=uid,
        hotkey=hotkey,
        coldkey=coldkey,
        model_family=model_family,
        hub_digest=hub_digest,
        revision=revision,
        commit_message=commit_message,
        meta=meta,
    )
    return AlertContent(
        kind="repo_new",
        title=f"[repo_new] {repo}",
        message=(
            f"SN{netuid} new hub repo"
            + (f" | digest {_short_digest(hub_digest)}" if hub_digest else "")
            + (f" | {revision}" if revision else "")
        ),
        source_key=f"alert:{source_key}",
        detail=detail,
        subnet=netuid,
    )


def build_repo_updated_alert(
    *,
    netuid: int,
    repo: str,
    event_type: str,
    source_key: str,
    uid: int | None = None,
    hotkey: str | None = None,
    coldkey: str | None = None,
    model_family: str | None = None,
    hub_digest: str | None = None,
    previous_digest: str | None = None,
    revision: str | None = None,
    commit_message: str | None = None,
    meta: dict[str, Any] | None = None,
) -> AlertContent:
    detail = repo_alert_detail(
        repo=repo,
        event_type=event_type,
        uid=uid,
        hotkey=hotkey,
        coldkey=coldkey,
        model_family=model_family,
        hub_digest=hub_digest,
        previous_digest=previous_digest,
        revision=revision,
        commit_message=commit_message,
        meta=meta,
    )
    return AlertContent(
        kind="repo_updated",
        title=f"[repo_updated] {repo}",
        message=(
            f"SN{netuid} hub manifest updated"
            + (f" | {_short_digest(previous_digest)} → {_short_digest(hub_digest)}" if hub_digest else "")
        ),
        source_key=f"alert:{source_key}",
        detail=detail,
        subnet=netuid,
    )


def build_crown_won_alert(
    *,
    netuid: int,
    source_key: str,
    detail: dict[str, Any],
    repo: str | None,
    model_uri: str | None,
    king_version: Any,
    defeated_king_version: Any,
) -> AlertContent:
    label = repo or model_uri or "unknown"
    return AlertContent(
        kind="crown_won",
        title=f"[crown_won] {label}",
        message=(
            f"SN{netuid} crowned king v{king_version or '?'} "
            f"(defeated v{defeated_king_version or '?'})"
        ),
        source_key=source_key,
        detail=detail,
        subnet=netuid,
    )


def build_crown_lost_alert(
    *,
    netuid: int,
    source_key: str,
    detail: dict[str, Any],
    previous_king_version: int,
    current_version: Any,
) -> AlertContent:
    return AlertContent(
        kind="crown_lost",
        title=f"[crown_lost] king v{previous_king_version}",
        message=f"SN{netuid} reign ended — current king is v{current_version}",
        source_key=source_key,
        detail=detail,
        subnet=netuid,
    )


def _duel_participant_detail(run: dict[str, Any], *, repo_from_uri) -> dict[str, Any]:
    king = run.get("king") or {}
    repo = repo_from_uri(run.get("model_uri"))
    king_repo = repo_from_uri(king.get("model_uri"))
    return {
        "eval_run_id": run.get("eval_run_id"),
        "repo": repo,
        "namespace": run.get("namespace") or (repo.split("/")[0] if repo else None),
        "uid": run.get("uid") or king.get("uid"),
        "hotkey": run.get("hotkey") or king.get("hotkey"),
        "model_uri": run.get("model_uri"),
        "king_version": run.get("king_version") or king.get("king_version"),
        "king_repo": king_repo,
        "score_challenger": run.get("score_challenger"),
        "score_king": run.get("score_king"),
        "win_margin": run.get("win_margin"),
        "finished_at": run.get("finished_at"),
        "challenger_won": run.get("challenger_won"),
        "coronated": run.get("coronated"),
    }


def build_duel_new_alert(
    *,
    netuid: int,
    source_key: str,
    current_eval: dict[str, Any],
    repo_from_uri,
    reign_king: dict[str, Any] | None,
) -> AlertContent:
    repo = repo_from_uri(current_eval.get("model_uri"))
    king = reign_king or {}
    king_repo = repo_from_uri(king.get("model_uri"))
    detail = {
        "eval_run_id": current_eval.get("eval_run_id"),
        "repo": repo,
        "namespace": repo.split("/")[0] if repo and "/" in repo else None,
        "uid": current_eval.get("uid"),
        "hotkey": current_eval.get("hotkey"),
        "model_uri": current_eval.get("model_uri"),
        "state": current_eval.get("state"),
        "king_version": king.get("king_version"),
        "king_repo": king_repo,
        "sample_count": current_eval.get("sample_count"),
        "started_at": current_eval.get("started_at"),
    }
    label = repo or current_eval.get("model_uri", "unknown")
    return AlertContent(
        kind="duel_new",
        title=f"[duel_new] {label}",
        message=f"SN{netuid} Albedo eval started — challenger vs king v{king.get('king_version', '?')}",
        source_key=source_key,
        detail={k: v for k, v in detail.items() if v is not None},
        subnet=netuid,
    )


def build_king_defended_alert(
    *,
    netuid: int,
    source_key: str,
    detail: dict[str, Any],
    repo: str | None,
) -> AlertContent:
    label = repo or detail.get("model_uri", "unknown")
    margin = detail.get("win_margin")
    margin_s = f" margin {margin:+.3f}" if margin is not None else ""
    return AlertContent(
        kind="king_defended",
        title=f"[king_defended] {label}",
        message=(
            f"SN{netuid} eval finished — king defended"
            f"{margin_s} (challenger lost eval)"
        ),
        source_key=source_key,
        detail=detail,
        subnet=netuid,
    )


def build_eval_dq_alert(
    *,
    netuid: int,
    source_key: str,
    detail: dict[str, Any],
    repo: str | None,
) -> AlertContent:
    label = repo or detail.get("model_uri") or "unknown"
    fault_code = detail.get("fault_code") or "?"
    fault_class = detail.get("fault_class") or "UNKNOWN"
    uid = detail.get("uid")
    uid_s = f"uid {uid} " if uid is not None else ""
    return AlertContent(
        kind="eval_dq",
        title=f"[eval_dq] {label}",
        message=(
            f"SN{netuid} {uid_s}added to DQ list — {fault_class} / {fault_code}"
        ),
        source_key=source_key,
        detail=detail,
        subnet=netuid,
        severity="high" if fault_class == "MINER_FAULT" else "medium",
    )


def build_reg_fee_low_alert(
    *,
    netuid: int,
    source_key: str,
    detail: dict[str, Any],
    burn: float,
    threshold: float,
) -> AlertContent:
    return AlertContent(
        kind="reg_fee_low",
        title=f"[reg_fee_low] SN{netuid} · below {threshold:g} τ",
        message=f"Registration burn *{burn:.4f} τ* crossed below *{threshold:g} τ* tier",
        source_key=source_key,
        detail=detail,
        subnet=netuid,
    )


def format_detail_lines(kind: AlertKind, detail: dict[str, Any]) -> list[str]:
    """Ordered, human-readable detail lines for Slack messages."""
    order = DETAIL_ORDER.get(kind, ())
    lines: list[str] = []
    seen: set[str] = set()

    def append(key: str) -> None:
        if key in seen:
            return
        value = detail.get(key)
        if value is None or value == "":
            return
        seen.add(key)
        label = key.replace("_", " ").title()
        if isinstance(value, (dict, list)):
            lines.append(f"*{label}:* `{value}`")
        else:
            lines.append(f"*{label}:* {value}")

    for key in order:
        append(key)
    for key in sorted(detail):
        append(key)
    return lines


def format_alert_body(kind: AlertKind, message: str, detail: dict[str, Any]) -> str:
    lines = [message, *format_detail_lines(kind, detail)]
    return "\n".join(lines)
