"""Structured Slack alerts — one emoji, multi-line body, no field grids."""

from __future__ import annotations

from typing import Any

from app.notifications.kinds import SLACK_EMOJI, AlertKind
from app.notifications.reg_fee_tiers import reg_fee_tier_emoji

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


def _short(s: str | None, n: int = 16) -> str:
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


def _kind_emoji(kind: AlertKind, detail: dict[str, Any]) -> str:
    if kind == "reg_fee_low":
        tier = detail.get("threshold_tao")
        if tier is not None:
            return reg_fee_tier_emoji(float(tier))
    return SLACK_EMOJI.get(kind, ":bell:")


def _headline(kind: AlertKind, subnet: int | None) -> str:
    label = _KIND_HEADLINE.get(kind, kind.replace("_", " ").title())
    sn = f"  ·  SN{subnet}" if subnet is not None else ""
    return f"*{label}*{sn}"


def _fmt_scores(detail: dict[str, Any]) -> str | None:
    ch = detail.get("score_challenger")
    kg = detail.get("score_king")
    if ch is None and kg is None:
        return None
    ch_s = f"{float(ch):.3f}" if ch is not None else "?"
    kg_s = f"{float(kg):.3f}" if kg is not None else "?"
    return f"Scores {ch_s} vs {kg_s}"


def _fmt_margin(detail: dict[str, Any]) -> str | None:
    margin = detail.get("win_margin")
    if margin is None:
        return None
    return f"Margin {float(margin):+.3f}"


def _join_bits(bits: list[str | None]) -> str | None:
    clean = [b for b in bits if b]
    return "  ·  ".join(clean) if clean else None


def _structured_body(kind: AlertKind, message: str, detail: dict[str, Any]) -> str:
    repo = _repo_from_detail(detail)
    repo_s = f"`{repo}`" if repo else "`?`"
    king_repo = detail.get("king_repo")
    king_repo_s = f"`{king_repo}`" if king_repo else None

    if kind == "duel_new":
        king_v = detail.get("king_version")
        lines = [
            f"*Challenger*\n{repo_s}",
            _join_bits(
                [
                    f"*King*  v{king_v}" if king_v is not None else "*King*",
                    king_repo_s,
                ]
            )
            or "",
            _join_bits(
                [
                    f"UID {detail['uid']}" if detail.get("uid") is not None else None,
                    str(detail["state"]) if detail.get("state") else None,
                    f"{detail['sample_count']} samples" if detail.get("sample_count") is not None else None,
                ]
            )
            or "",
        ]
        return "\n\n".join(line for line in lines if line)

    if kind == "crown_won":
        king_v = detail.get("king_version")
        defeated_v = detail.get("defeated_king_version")
        version_line = None
        if king_v is not None and defeated_v is not None:
            version_line = f"Defeated king v{defeated_v}  →  crowned v{king_v}"
        elif king_v is not None:
            version_line = f"Crowned king v{king_v}"
        lines = [
            f"*Champion*\n{repo_s}",
            version_line or "",
            _join_bits([_fmt_margin(detail), _fmt_scores(detail)]) or "",
            _join_bits(
                [
                    f"UID {detail['uid']}" if detail.get("uid") is not None else None,
                    f"run `{_short(str(detail['eval_run_id']), 8)}`" if detail.get("eval_run_id") else None,
                ]
            )
            or "",
        ]
        return "\n\n".join(line for line in lines if line)

    if kind == "king_defended":
        king_v = detail.get("king_version")
        king_line = _join_bits(
            [
                f"King v{king_v} held" if king_v is not None else "King held",
                king_repo_s,
            ]
        )
        lines = [
            f"*Challenger*\n{repo_s}",
            king_line or "",
            _join_bits([_fmt_margin(detail), _fmt_scores(detail)]) or "",
            _join_bits(
                [
                    f"UID {detail['uid']}" if detail.get("uid") is not None else None,
                    f"run `{_short(str(detail['eval_run_id']), 8)}`" if detail.get("eval_run_id") else None,
                ]
            )
            or "",
        ]
        return "\n\n".join(line for line in lines if line)

    if kind == "crown_lost":
        prev_v = detail.get("previous_king_version")
        new_v = detail.get("new_king_version")
        new_repo = detail.get("new_repo")
        new_s = f"`{new_repo}`" if new_repo else "`?`"
        return (
            f"Reign ended at king v{prev_v}\n\n"
            f"*Successor*  v{new_v}  ·  {new_s}"
        )

    if kind in ("commit_new", "commit_updated"):
        digest = detail.get("digest") or detail.get("hub_digest")
        d = _short(str(digest).replace("sha256:", ""), 12) if digest else "?"
        return "\n\n".join(
            line
            for line in [
                f"*Repo*\n{repo_s}" if repo else None,
                _join_bits(
                    [
                        f"UID {detail['uid']}" if detail.get("uid") is not None else None,
                        f"block {detail['commit_block']}" if detail.get("commit_block") else None,
                        f"`{d}`",
                    ]
                ),
            ]
            if line
        )

    if kind in ("slot_new", "slot_changed"):
        model = detail.get("detail") or repo or "?"
        return "\n\n".join(
            line
            for line in [
                f"*Model*\n`{model}`",
                _join_bits(
                    [
                        f"UID {detail['uid']}" if detail.get("uid") is not None else None,
                        f"block {detail['commit_block']}" if detail.get("commit_block") else None,
                    ]
                ),
            ]
            if line
        )

    if kind in ("repo_new", "repo_updated"):
        digest = detail.get("digest") or detail.get("hub_digest")
        d = _short(str(digest).replace("sha256:", ""), 12) if digest else "?"
        fam = detail.get("model_family")
        return "\n\n".join(
            line
            for line in [
                f"*Repo*\n{repo_s}",
                _join_bits([fam, f"`{d}`" if d != "?" else None]),
            ]
            if line
        )

    if kind == "reg_fee_low":
        burn = detail.get("registration_burn_tao")
        tier = detail.get("threshold_tao")
        burn_s = f"{float(burn):.4f}" if burn is not None else "?"
        tier_s = f"{float(tier):g}" if tier is not None else "?"
        extra = _join_bits(
            [
                f"α {float(detail['alpha_price_tao']):.4f} τ"
                if detail.get("alpha_price_tao") is not None
                else None,
                f"block {detail['chain_block']}" if detail.get("chain_block") is not None else None,
            ]
        )
        lines = [
            f"Burn dropped to *{burn_s} τ*",
            f"Crossed below *{tier_s} τ* alert tier",
            extra or "",
        ]
        return "\n\n".join(line for line in lines if line)

    return message[:300]


def _link_line(detail: dict[str, Any], subnet: int | None) -> str:
    parts: list[str] = []
    repo = _repo_from_detail(detail)
    if repo:
        parts.append(f"<{hippius_repo_url(repo)}|Hippius>")
        parts.append(f"<{huggingface_repo_url(repo)}|HF>")
    if subnet is not None:
        parts.append(f"<{taostats_subnet_url(subnet)}|SN{subnet}>")
    return "  ·  ".join(parts)


def build_slack_payload(
    *,
    kind: AlertKind,
    title: str,
    message: str,
    detail: dict[str, Any],
    subnet: int | None,
) -> dict[str, Any]:
    emoji = _kind_emoji(kind, detail)
    headline = _headline(kind, subnet)
    body = _structured_body(kind, message, detail)
    links = _link_line(detail, subnet)

    # Emoji appears exactly once — on the title line only.
    main = f"{emoji}  {headline}\n\n{body}"

    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": main[:3000]}},
    ]
    if links:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": links}]})

    plain = f"{emoji} {_KIND_HEADLINE.get(kind, kind)} — {body.replace(chr(10), ' ')[:200]}"
    return {"text": plain[:500], "blocks": blocks}
