"""Human-readable Slack alerts — plain language, full URLs, one emoji."""

from __future__ import annotations

from typing import Any

from app.notifications.kinds import SLACK_EMOJI, AlertKind
from app.notifications.reg_fee_tiers import reg_fee_tier_emoji


def hippius_repo_url(repo: str, revision: str = "main") -> str:
    return f"https://hub.hippius.com/models/{repo.strip()}/{revision}"


def huggingface_repo_url(repo: str) -> str:
    return f"https://huggingface.co/{repo.strip()}"


def taostats_subnet_url(subnet: int) -> str:
    return f"https://taostats.io/subnets/{subnet}"


def _subnet_label(subnet: int | None) -> str:
    return f"Subnet {subnet}" if subnet is not None else "the subnet"


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


def _miner_label(detail: dict[str, Any], repo: str | None = None) -> str:
    repo = repo or _repo_from_detail(detail) or "unknown model"
    uid = detail.get("uid")
    if uid is not None:
        return f"{repo} (UID {uid})"
    return repo


def _digest_label(detail: dict[str, Any]) -> str | None:
    raw = detail.get("digest") or detail.get("hub_digest")
    if not raw:
        return None
    text = str(raw).replace("sha256:", "")
    if len(text) > 20:
        return f"sha256:{text[:20]}…"
    return f"sha256:{text}"


def _kind_emoji(kind: AlertKind, detail: dict[str, Any]) -> str:
    if kind == "reg_fee_low":
        tier = detail.get("threshold_tao")
        if tier is not None:
            return reg_fee_tier_emoji(float(tier))
    return SLACK_EMOJI.get(kind, ":bell:")


def _title_line(kind: AlertKind, subnet: int | None) -> str:
    sn = _subnet_label(subnet)
    titles: dict[AlertKind, str] = {
        "duel_new": f"New duel started on {sn}",
        "crown_won": f"A new king was crowned on {sn}",
        "king_defended": f"The king defended the crown on {sn}",
        "crown_lost": f"The reigning king was replaced on {sn}",
        "commit_new": f"New on-chain model commit on {sn}",
        "commit_updated": f"Model commit updated on {sn}",
        "slot_new": f"A miner purchased a slot on {sn}",
        "slot_changed": f"A miner purchased a slot on {sn}",
        "repo_new": f"New Albedo repo detected on {sn}",
        "repo_updated": f"Albedo repo updated on {sn}",
        "reg_fee_low": f"Registration fee alert on {sn}",
    }
    return titles.get(kind, f"Alert on {sn}")


def _score_sentence(detail: dict[str, Any]) -> str | None:
    ch = detail.get("score_challenger")
    kg = detail.get("score_king")
    margin = detail.get("win_margin")
    if ch is None and kg is None:
        return None
    ch_s = f"{float(ch):.3f}" if ch is not None else "unknown"
    kg_s = f"{float(kg):.3f}" if kg is not None else "unknown"
    sentence = (
        f"The challenger scored {ch_s} and the king scored {kg_s}."
    )
    if margin is not None:
        m = float(margin)
        if m > 0:
            sentence += f" The challenger won by a margin of {m:+.3f}."
        elif m < 0:
            sentence += f" The king won by a margin of {abs(m):.3f}."
        else:
            sentence += " The duel ended in a tie."
    return sentence


def _write_prose(kind: AlertKind, message: str, detail: dict[str, Any], subnet: int | None) -> str:
    repo = _repo_from_detail(detail)
    king_repo = detail.get("king_repo")
    paragraphs: list[str] = []

    if kind == "duel_new":
        challenger = _miner_label(detail, repo)
        king_v = detail.get("king_version")
        king_part = (
            f"{king_repo} at king version {king_v}"
            if king_repo and king_v is not None
            else (f"king version {king_v}" if king_v is not None else "the current king")
        )
        paragraphs.append(
            f"{challenger} has started a new duel against {king_part}."
        )
        state = detail.get("state")
        samples = detail.get("sample_count")
        status_bits: list[str] = []
        if state:
            status_bits.append(f"status is {state}")
        if samples is not None:
            status_bits.append(f"{samples} samples are queued")
        if status_bits:
            paragraphs.append(
                "The evaluation " + " and ".join(status_bits) + "."
            )

    elif kind == "crown_won":
        winner = _miner_label(detail, repo)
        king_v = detail.get("king_version")
        defeated_v = detail.get("defeated_king_version")
        if king_v is not None and defeated_v is not None:
            paragraphs.append(
                f"{winner} won the duel and was crowned the new king "
                f"at version {king_v}, replacing king version {defeated_v}."
            )
        elif king_v is not None:
            paragraphs.append(
                f"{winner} won the duel and was crowned the new king at version {king_v}."
            )
        else:
            paragraphs.append(f"{winner} won the duel and was crowned the new king.")
        score_line = _score_sentence(detail)
        if score_line:
            paragraphs.append(score_line)

    elif kind == "king_defended":
        challenger = _miner_label(detail, repo)
        king_v = detail.get("king_version")
        king_name = king_repo or "the reigning king"
        if king_v is not None:
            paragraphs.append(
                f"{challenger} challenged {king_name} (king version {king_v}) "
                f"but did not take the crown."
            )
        else:
            paragraphs.append(
                f"{challenger} challenged the reigning king but did not take the crown."
            )
        score_line = _score_sentence(detail)
        if score_line:
            paragraphs.append(score_line)

    elif kind == "crown_lost":
        prev_v = detail.get("previous_king_version")
        new_v = detail.get("new_king_version")
        new_repo = detail.get("new_repo") or "an unknown model"
        paragraphs.append(
            f"King version {prev_v} is no longer on the throne. "
            f"The current king is version {new_v}: {new_repo}."
        )

    elif kind == "commit_new":
        miner = _miner_label(detail, repo)
        block = detail.get("commit_block")
        block_s = f" at block {block}" if block is not None else ""
        paragraphs.append(
            f"{miner} published a new on-chain model commitment{block_s}."
        )
        digest = _digest_label(detail)
        if digest:
            paragraphs.append(f"Commit digest: {digest}")

    elif kind == "commit_updated":
        miner = _miner_label(detail, repo)
        block = detail.get("commit_block")
        block_s = f" at block {block}" if block is not None else ""
        paragraphs.append(
            f"{miner} updated an existing on-chain model commitment{block_s}."
        )
        digest = _digest_label(detail)
        if digest:
            paragraphs.append(f"New digest: {digest}")

    elif kind in ("slot_new", "slot_changed"):
        miner = _miner_label(detail, repo)
        model = detail.get("detail") or repo or "a new model slot"
        block = detail.get("commit_block")
        block_s = f" at block {block}" if block is not None else ""
        paragraphs.append(
            f"{miner} purchased a block slot{block_s} for {model}."
        )

    elif kind == "repo_new":
        name = repo or "a new repository"
        fam = detail.get("model_family")
        fam_s = f" ({fam})" if fam else ""
        paragraphs.append(
            f"A new Albedo model repository appeared on the Hippius hub: {name}{fam_s}."
        )
        digest = _digest_label(detail)
        if digest:
            paragraphs.append(f"Hub manifest digest: {digest}")

    elif kind == "repo_updated":
        name = repo or "a repository"
        paragraphs.append(
            f"The Hippius hub manifest was updated for {name}."
        )
        digest = _digest_label(detail)
        if digest:
            paragraphs.append(f"New digest: {digest}")

    elif kind == "reg_fee_low":
        burn = detail.get("registration_burn_tao")
        tier = detail.get("threshold_tao")
        burn_s = f"{float(burn):.4f}" if burn is not None else "unknown"
        tier_s = f"{float(tier):g}" if tier is not None else "unknown"
        paragraphs.append(
            f"The registration burn is now {burn_s} τ, which is below your "
            f"{tier_s} τ alert threshold."
        )
        paragraphs.append(
            "If you were waiting for a lower registration cost, this may be a good time to register."
        )
        alpha = detail.get("alpha_price_tao")
        block = detail.get("chain_block")
        extras: list[str] = []
        if alpha is not None:
            extras.append(f"alpha price is {float(alpha):.4f} τ")
        if block is not None:
            extras.append(f"chain block {block}")
        if extras:
            paragraphs.append("Current " + " and ".join(extras) + ".")

    else:
        paragraphs.append(message[:400])

    return "\n\n".join(paragraphs)


def _collect_urls(detail: dict[str, Any], subnet: int | None) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []

    def add(url: str) -> None:
        if url not in seen:
            seen.add(url)
            urls.append(url)

    repo = _repo_from_detail(detail)
    if repo:
        add(hippius_repo_url(repo))
        add(huggingface_repo_url(repo))

    king_repo = detail.get("king_repo")
    if king_repo and king_repo != repo:
        add(hippius_repo_url(str(king_repo)))
        add(huggingface_repo_url(str(king_repo)))

    new_repo = detail.get("new_repo")
    if new_repo and new_repo not in (repo, king_repo):
        add(hippius_repo_url(str(new_repo)))
        add(huggingface_repo_url(str(new_repo)))

    if subnet is not None:
        add(taostats_subnet_url(subnet))

    return urls


def _links_block(urls: list[str]) -> str:
    if not urls:
        return ""
    return "Useful links:\n" + "\n".join(urls)


def build_slack_payload(
    *,
    kind: AlertKind,
    title: str,
    message: str,
    detail: dict[str, Any],
    subnet: int | None,
) -> dict[str, Any]:
    emoji = _kind_emoji(kind, detail)
    heading = _title_line(kind, subnet)
    prose = _write_prose(kind, message, detail, subnet)
    urls = _collect_urls(detail, subnet)
    links = _links_block(urls)

    main = f"{emoji} *{heading}*\n\n{prose}"
    if links:
        main = f"{main}\n\n{links}"

    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": main[:3000]}},
    ]

    plain_body = prose.replace("\n\n", " ")
    fallback = f"{heading} — {plain_body[:300]}"
    if urls:
        fallback = f"{fallback} {urls[0]}"
    return {"text": fallback[:500], "blocks": blocks}
