"""Human-readable Slack alerts — one emoji, one link, Bittensor-accurate copy."""

from __future__ import annotations

from typing import Any

from app.notifications.kinds import SLACK_EMOJI, AlertKind
from app.notifications.reg_fee_tiers import reg_fee_tier_emoji
from app.notifications.terminology import prose_for, repo_from_detail, title_for


def hippius_repo_url(repo: str, revision: str = "main") -> str:
    return f"https://hub.hippius.com/models/{repo.strip()}/{revision}"


def taostats_subnet_url(subnet: int) -> str:
    return f"https://taostats.io/subnets/{subnet}"


def _kind_emoji(kind: AlertKind, detail: dict[str, Any]) -> str:
    if kind == "reg_fee_low":
        tier = detail.get("threshold_tao")
        if tier is not None:
            return reg_fee_tier_emoji(float(tier))
    return SLACK_EMOJI.get(kind, ":bell:")


def _primary_url(kind: AlertKind, detail: dict[str, Any], subnet: int | None) -> str | None:
    if kind == "reg_fee_low":
        return taostats_subnet_url(subnet) if subnet is not None else None
    if kind == "crown_lost":
        new_repo = detail.get("new_repo")
        if new_repo:
            return hippius_repo_url(str(new_repo))
    repo = repo_from_detail(detail)
    if repo:
        return hippius_repo_url(repo)
    return taostats_subnet_url(subnet) if subnet is not None else None


def build_slack_payload(
    *,
    kind: AlertKind,
    title: str,
    message: str,
    detail: dict[str, Any],
    subnet: int | None,
) -> dict[str, Any]:
    emoji = _kind_emoji(kind, detail)
    heading = title_for(kind, subnet, detail)
    prose = prose_for(kind, message, detail)
    url = _primary_url(kind, detail, subnet)

    main = f"{emoji} *{heading}*\n\n{prose}"
    if url:
        main = f"{main}\n\n{url}"

    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": main[:3000]}},
    ]

    plain = prose.replace("\n\n", " ")
    fallback = f"{heading} — {plain[:280]}"
    if url:
        fallback = f"{fallback} {url}"
    return {"text": fallback[:500], "blocks": blocks}
