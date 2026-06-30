"""Compact, visual Slack block payloads for alerts."""

from __future__ import annotations

import re
from typing import Any

from app.notifications.kinds import SLACK_EMOJI, AlertKind
from app.notifications.messages import KIND_LABELS
from app.notifications.reg_fee_tiers import reg_fee_tier_emoji

_TITLE_TAG_RE = re.compile(r"^\[[\w_]+\]\s*")


def hippius_repo_url(repo: str, revision: str = "main") -> str:
    return f"https://hub.hippius.com/models/{repo.strip()}/{revision}"


def huggingface_repo_url(repo: str) -> str:
    return f"https://huggingface.co/{repo.strip()}"


def taostats_subnet_url(subnet: int) -> str:
    return f"https://taostats.io/subnets/{subnet}"


def _short(s: str | None, n: int = 14) -> str:
    if not s:
        return "—"
    text = str(s)
    return text if len(text) <= n else f"{text[:n]}…"


def _subject_from_title(title: str) -> str:
    return _TITLE_TAG_RE.sub("", title).strip()


def _repo_from_detail(detail: dict[str, Any]) -> str | None:
    for key in ("repo", "detail", "king_repo", "new_repo", "model_uri"):
        raw = detail.get(key)
        if not raw:
            continue
        text = str(raw)
        if "@" in text:
            text = text.split("@", 1)[0]
        if "/" in text:
            return text
    return None


def _link_line(kind: AlertKind, detail: dict[str, Any], subnet: int | None) -> str:
    parts: list[str] = []
    repo = _repo_from_detail(detail)
    if repo:
        parts.append(f"<{hippius_repo_url(repo)}|Hippius>")
        parts.append(f"<{huggingface_repo_url(repo)}|HF>")
    if subnet is not None:
        parts.append(f"<{taostats_subnet_url(subnet)}|SN{subnet}>")
    eval_id = detail.get("eval_run_id")
    if eval_id and kind in ("duel_new", "crown_won", "king_defended"):
        parts.append(f"`{str(eval_id)[:8]}…`")
    return " · ".join(parts)


def _compact_summary(kind: AlertKind, message: str, detail: dict[str, Any]) -> str:
    repo = _repo_from_detail(detail)
    uid = detail.get("uid")
    block = detail.get("commit_block")
    digest = detail.get("digest") or detail.get("hub_digest")
    king_v = detail.get("king_version")
    king_repo = detail.get("king_repo")

    if kind == "duel_new":
        vs = f" vs king v{king_v}" if king_v is not None else ""
        king = f" ({king_repo})" if king_repo else ""
        return f"*{repo or '?'}*{vs}{king}"
    if kind in ("commit_new", "commit_updated"):
        d = _short(str(digest).replace("sha256:", ""), 12) if digest else "?"
        return f"uid *{uid}* · block *{block}* · `{d}`"
    if kind in ("slot_new", "slot_changed"):
        model = detail.get("detail") or repo or "?"
        return f"uid *{uid}* · block *{block}* · `{model}`"
    if kind in ("repo_new", "repo_updated"):
        d = _short(str(digest).replace("sha256:", ""), 12) if digest else "?"
        return f"*{repo or '?'}* · `{d}`"
    if kind == "crown_won":
        return message.split("—")[0].strip()[:200]
    if kind == "crown_lost":
        return message[:200]
    if kind == "king_defended":
        margin = detail.get("win_margin")
        m = f" · margin {margin:+.3f}" if margin is not None else ""
        return f"King held{m}"
    if kind == "reg_fee_low":
        tier = detail.get("threshold_tao")
        burn = detail.get("registration_burn_tao")
        return f"Burn *{burn}* τ · crossed below *{tier:g} τ* tier"
    return message[:240]


def _fields_for_kind(kind: AlertKind, detail: dict[str, Any], subnet: int | None) -> list[dict[str, str]]:
    fields: list[tuple[str, Any]] = []

    def add(label: str, key: str) -> None:
        val = detail.get(key)
        if val is not None and val != "":
            fields.append((label, val))

    if kind in ("commit_new", "commit_updated"):
        add("UID", "uid")
        add("Block", "commit_block")
        add("Version", "version")
        add("Hotkey", "hotkey")
    elif kind == "duel_new":
        add("UID", "uid")
        add("State", "state")
        add("King v", "king_version")
        add("Samples", "sample_count")
    elif kind in ("slot_new", "slot_changed"):
        add("UID", "uid")
        add("Block", "commit_block")
        add("Type", "commitment_type")
    elif kind in ("repo_new", "repo_updated"):
        add("Family", "model_family")
        add("Revision", "revision")
        add("UID", "uid")
    elif kind == "reg_fee_low":
        add("Burn τ", "registration_burn_tao")
        add("Tier τ", "threshold_tao")
        add("Alpha", "alpha_price_tao")
        add("Block", "chain_block")

    if subnet is not None and kind not in ("reg_fee_low",):
        fields.append(("Subnet", f"SN{subnet}"))

    out: list[dict[str, str]] = []
    for label, val in fields[:8]:
        if isinstance(val, float):
            text = f"{val:.4f}" if label.endswith("τ") else f"{val}"
        else:
            text = _short(str(val), 22) if label == "Hotkey" else str(val)
        out.append({"type": "mrkdwn", "text": f"*{label}*\n{text}"})
    return out


def build_slack_payload(
    *,
    kind: AlertKind,
    title: str,
    message: str,
    detail: dict[str, Any],
    subnet: int | None,
) -> dict[str, Any]:
    emoji = SLACK_EMOJI.get(kind, ":bell:")
    if kind == "reg_fee_low":
        tier = detail.get("threshold_tao")
        if tier is not None:
            emoji = reg_fee_tier_emoji(float(tier))
    label = KIND_LABELS.get(kind, kind)
    subject = _subject_from_title(title)
    header = f"{emoji} {label} · {subject}"[:150]
    summary = _compact_summary(kind, message, detail)
    fields = _fields_for_kind(kind, detail, subnet)
    links = _link_line(kind, detail, subnet)

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": header, "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{emoji} {summary}"}},
    ]
    if fields:
        blocks.append({"type": "section", "fields": fields})
    if links:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": links}]})

    fallback = f"{header}\n{summary}"
    if links:
        fallback = f"{fallback}\n{links}"
    return {"text": fallback[:500], "blocks": blocks}
