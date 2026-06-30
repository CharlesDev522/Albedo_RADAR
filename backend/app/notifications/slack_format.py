"""Clean Slack block payloads — single rich section, no bulky headers."""

from __future__ import annotations

import re
from typing import Any

from app.notifications.kinds import SLACK_EMOJI, AlertKind
from app.notifications.reg_fee_tiers import reg_fee_tier_emoji

_TITLE_TAG_RE = re.compile(r"^\[[\w_]+\]\s*")

_KIND_HEADLINE: dict[AlertKind, str] = {
    "crown_won": "New King",
    "crown_lost": "King Dethroned",
    "duel_new": "Duel Started",
    "king_defended": "King Defended",
    "slot_new": "Slot Purchased",
    "slot_changed": "Slot Purchased",
    "commit_new": "New Commit",
    "commit_updated": "Commit Updated",
    "repo_new": "New Repo",
    "repo_updated": "Repo Updated",
    "reg_fee_low": "Reg Fee Drop",
}


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


def _fmt_scores(detail: dict[str, Any]) -> str | None:
    ch = detail.get("score_challenger")
    kg = detail.get("score_king")
    if ch is None and kg is None:
        return None
    ch_s = f"{float(ch):.3f}" if ch is not None else "?"
    kg_s = f"{float(kg):.3f}" if kg is not None else "?"
    return f"scores {ch_s} vs {kg_s}"


def _fmt_margin(detail: dict[str, Any]) -> str | None:
    margin = detail.get("win_margin")
    if margin is None:
        return None
    return f"margin {float(margin):+.3f}"


def _headline(kind: AlertKind, detail: dict[str, Any], subnet: int | None) -> str:
    emoji = SLACK_EMOJI.get(kind, ":bell:")
    if kind == "reg_fee_low":
        tier = detail.get("threshold_tao")
        if tier is not None:
            emoji = reg_fee_tier_emoji(float(tier))
    label = _KIND_HEADLINE.get(kind, kind.replace("_", " ").title())
    sn = f" · SN{subnet}" if subnet is not None else ""
    return f"{emoji} *{label}*{sn}"


def _body_line(kind: AlertKind, message: str, detail: dict[str, Any]) -> str:
    repo = _repo_from_detail(detail)
    repo_s = f"`{repo}`" if repo else None
    uid = detail.get("uid")
    block = detail.get("commit_block")
    digest = detail.get("digest") or detail.get("hub_digest")
    king_v = detail.get("king_version")
    defeated_v = detail.get("defeated_king_version")
    king_repo = detail.get("king_repo")
    scores = _fmt_scores(detail)
    margin = _fmt_margin(detail)

    if kind == "duel_new":
        vs = f" vs king v{king_v}" if king_v is not None else ""
        king = f" (`{king_repo}`)" if king_repo else ""
        return f"Challenger {repo_s or '?'} started{vs}{king}"

    if kind == "crown_won":
        vers = ""
        if king_v is not None and defeated_v is not None:
            vers = f" · v{king_v} ← defeated v{defeated_v}"
        elif king_v is not None:
            vers = f" · crowned v{king_v}"
        parts = [p for p in [repo_s, vers.strip() if vers else None, margin, scores] if p]
        return " · ".join(parts) if parts else message[:200]

    if kind == "king_defended":
        parts = [f"Challenger {repo_s or '?'} failed"]
        if king_v is not None:
            parts.append(f"king v{king_v} held")
        if margin:
            parts.append(margin)
        if scores:
            parts.append(scores)
        return " · ".join(parts)

    if kind == "crown_lost":
        prev_v = detail.get("previous_king_version")
        new_v = detail.get("new_king_version")
        new_repo = detail.get("new_repo")
        new_s = f"`{new_repo}`" if new_repo else "?"
        return f"Reign v{prev_v} ended · new king v{new_v} is {new_s}"

    if kind in ("commit_new", "commit_updated"):
        d = _short(str(digest).replace("sha256:", ""), 12) if digest else "?"
        return f"uid *{uid}* · block *{block}* · `{d}`" + (f" · {repo_s}" if repo_s else "")

    if kind in ("slot_new", "slot_changed"):
        model = detail.get("detail") or repo or "?"
        return f"uid *{uid}* · block *{block}* · `{model}`"

    if kind in ("repo_new", "repo_updated"):
        d = _short(str(digest).replace("sha256:", ""), 12) if digest else "?"
        fam = detail.get("model_family")
        fam_s = f" · {fam}" if fam else ""
        return f"{repo_s or '?'}{fam_s} · `{d}`"

    if kind == "reg_fee_low":
        burn = detail.get("registration_burn_tao")
        tier = detail.get("threshold_tao")
        burn_s = f"{float(burn):.4f}" if burn is not None else "?"
        tier_s = f"{float(tier):g}" if tier is not None else "?"
        return f"Burn *{burn_s} τ* crossed below *{tier_s} τ* tier"

    return message[:240]


def _meta_line(kind: AlertKind, detail: dict[str, Any]) -> str | None:
    bits: list[str] = []
    if kind in ("duel_new", "crown_won", "king_defended"):
        if detail.get("uid") is not None:
            bits.append(f"uid {detail['uid']}")
        if detail.get("hotkey"):
            bits.append(f"hk `{_short(str(detail['hotkey']), 18)}`")
        eval_id = detail.get("eval_run_id")
        if eval_id:
            bits.append(f"run `{str(eval_id)[:8]}`")
    elif kind in ("commit_new", "commit_updated", "slot_new", "slot_changed"):
        if detail.get("hotkey"):
            bits.append(f"hk `{_short(str(detail['hotkey']), 18)}`")
        if detail.get("version"):
            bits.append(str(detail["version"]))
    elif kind == "reg_fee_low":
        if detail.get("alpha_price_tao") is not None:
            bits.append(f"α {float(detail['alpha_price_tao']):.4f} τ")
        if detail.get("chain_block") is not None:
            bits.append(f"block {detail['chain_block']}")
    return " · ".join(bits) if bits else None


def _link_line(kind: AlertKind, detail: dict[str, Any], subnet: int | None) -> str:
    parts: list[str] = []
    repo = _repo_from_detail(detail)
    if repo:
        parts.append(f"<{hippius_repo_url(repo)}|Hippius>")
        parts.append(f"<{huggingface_repo_url(repo)}|HF>")
    if subnet is not None:
        parts.append(f"<{taostats_subnet_url(subnet)}|SN{subnet}>")
    return " · ".join(parts)


def build_slack_payload(
    *,
    kind: AlertKind,
    title: str,
    message: str,
    detail: dict[str, Any],
    subnet: int | None,
) -> dict[str, Any]:
    headline = _headline(kind, detail, subnet)
    body = _body_line(kind, message, detail)
    meta = _meta_line(kind, detail)
    links = _link_line(kind, detail, subnet)

    main = f"{headline}\n{body}"
    if meta:
        main = f"{main}\n_{meta}_"

    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": main[:3000]}},
    ]
    if links:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": links}]})

    fallback = f"{headline} — {body}"
    if links:
        fallback = f"{fallback} ({links})"
    return {"text": fallback[:500], "blocks": blocks}
