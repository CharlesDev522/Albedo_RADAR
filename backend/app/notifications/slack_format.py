"""Human-readable Slack alerts — one emoji, one link, clear titles."""

from __future__ import annotations

from typing import Any

from app.notifications.kinds import SLACK_EMOJI, AlertKind
from app.notifications.reg_fee_tiers import reg_fee_tier_emoji


def hippius_repo_url(repo: str, revision: str = "main") -> str:
    return f"https://hub.hippius.com/models/{repo.strip()}/{revision}"


def taostats_subnet_url(subnet: int) -> str:
    return f"https://taostats.io/subnets/{subnet}"


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


def _uid(detail: dict[str, Any]) -> int | None:
    uid = detail.get("uid")
    return int(uid) if uid is not None else None


def _miner_label(detail: dict[str, Any], repo: str | None = None) -> str:
    repo = repo or _repo_from_detail(detail) or "unknown model"
    uid = _uid(detail)
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


def _title_line(kind: AlertKind, subnet: int | None, detail: dict[str, Any]) -> str:
    uid = _uid(detail)
    repo = _repo_from_detail(detail)
    sn = f"SN{subnet}" if subnet is not None else "subnet"

    if kind == "duel_new":
        return f"UID {uid} started a duel on {sn}" if uid is not None else f"New duel on {sn}"

    if kind == "crown_won":
        return f"UID {uid} crowned as new king on {sn}" if uid is not None else f"New king crowned on {sn}"

    if kind == "king_defended":
        return (
            f"UID {uid} lost the duel — king defended on {sn}"
            if uid is not None
            else f"King defended the crown on {sn}"
        )

    if kind == "crown_lost":
        prev = detail.get("previous_king_version")
        return f"King v{prev} was replaced on {sn}" if prev is not None else f"King replaced on {sn}"

    if kind == "commit_new":
        if uid is not None and repo:
            return f"UID {uid} committed {repo}"
        if uid is not None:
            return f"UID {uid} committed a new model"
        return f"New model commitment on {sn}"

    if kind == "commit_updated":
        if uid is not None and repo:
            return f"UID {uid} updated commit for {repo}"
        if uid is not None:
            return f"UID {uid} updated their model commit"
        return f"Model commitment updated on {sn}"

    if kind in ("slot_new", "slot_changed"):
        return f"UID {uid} bought a block slot on {sn}" if uid is not None else f"Block slot purchased on {sn}"

    if kind == "repo_new":
        return f"New repo: {repo}" if repo else f"New Albedo repo on {sn}"

    if kind == "repo_updated":
        return f"Repo updated: {repo}" if repo else f"Albedo repo updated on {sn}"

    if kind == "reg_fee_low":
        tier = detail.get("threshold_tao")
        tier_s = f"{float(tier):g} τ" if tier is not None else "alert level"
        return f"{sn} registration fee below {tier_s}"

    return f"Alert on {sn}"


def _score_sentence(detail: dict[str, Any]) -> str | None:
    ch = detail.get("score_challenger")
    kg = detail.get("score_king")
    margin = detail.get("win_margin")
    if ch is None and kg is None:
        return None
    ch_s = f"{float(ch):.3f}" if ch is not None else "unknown"
    kg_s = f"{float(kg):.3f}" if kg is not None else "unknown"
    sentence = f"The challenger scored {ch_s} and the king scored {kg_s}."
    if margin is not None:
        m = float(margin)
        if m > 0:
            sentence += f" The challenger won by {m:+.3f}."
        elif m < 0:
            sentence += f" The king won by {abs(m):.3f}."
        else:
            sentence += " The duel was a tie."
    return sentence


def _write_prose(kind: AlertKind, message: str, detail: dict[str, Any]) -> str:
    repo = _repo_from_detail(detail)
    king_repo = detail.get("king_repo")
    paragraphs: list[str] = []

    if kind == "duel_new":
        challenger = _miner_label(detail, repo)
        king_v = detail.get("king_version")
        king_part = (
            f"{king_repo} (king v{king_v})"
            if king_repo and king_v is not None
            else (f"king version {king_v}" if king_v is not None else "the current king")
        )
        paragraphs.append(f"{challenger} is now dueling {king_part}.")
        state = detail.get("state")
        samples = detail.get("sample_count")
        if state and samples is not None:
            paragraphs.append(f"Eval status is {state} with {samples} samples queued.")
        elif state:
            paragraphs.append(f"Eval status is {state}.")
        elif samples is not None:
            paragraphs.append(f"{samples} samples are in the queue.")

    elif kind == "crown_won":
        winner = _miner_label(detail, repo)
        king_v = detail.get("king_version")
        defeated_v = detail.get("defeated_king_version")
        if king_v is not None and defeated_v is not None:
            paragraphs.append(
                f"{winner} won and is now king version {king_v}, replacing version {defeated_v}."
            )
        elif king_v is not None:
            paragraphs.append(f"{winner} won and is now king version {king_v}.")
        else:
            paragraphs.append(f"{winner} won the duel and took the crown.")
        if line := _score_sentence(detail):
            paragraphs.append(line)

    elif kind == "king_defended":
        challenger = _miner_label(detail, repo)
        king_v = detail.get("king_version")
        king_name = king_repo or "the reigning king"
        if king_v is not None:
            paragraphs.append(
                f"{challenger} challenged {king_name} (king v{king_v}) but the king kept the crown."
            )
        else:
            paragraphs.append(f"{challenger} challenged the king but did not win.")
        if line := _score_sentence(detail):
            paragraphs.append(line)

    elif kind == "crown_lost":
        prev_v = detail.get("previous_king_version")
        new_v = detail.get("new_king_version")
        new_repo = detail.get("new_repo") or "unknown model"
        paragraphs.append(
            f"King version {prev_v} ended. The throne now belongs to version {new_v}: {new_repo}."
        )

    elif kind == "commit_new":
        miner = _miner_label(detail, repo)
        block = detail.get("commit_block")
        block_s = f" at block {block}" if block is not None else ""
        paragraphs.append(f"{miner} registered a new on-chain model commitment{block_s}.")
        if digest := _digest_label(detail):
            paragraphs.append(f"Digest: {digest}")

    elif kind == "commit_updated":
        miner = _miner_label(detail, repo)
        block = detail.get("commit_block")
        block_s = f" at block {block}" if block is not None else ""
        paragraphs.append(f"{miner} changed their on-chain model commitment{block_s}.")
        if digest := _digest_label(detail):
            paragraphs.append(f"New digest: {digest}")

    elif kind in ("slot_new", "slot_changed"):
        miner = _miner_label(detail, repo)
        model = detail.get("detail") or repo or "a model slot"
        block = detail.get("commit_block")
        block_s = f" at block {block}" if block is not None else ""
        paragraphs.append(f"{miner} bought a block slot{block_s} for {model}.")

    elif kind == "repo_new":
        name = repo or "a new repository"
        fam = detail.get("model_family")
        extra = f" ({fam})" if fam else ""
        paragraphs.append(f"New Albedo repo on Hippius: {name}{extra}.")
        if digest := _digest_label(detail):
            paragraphs.append(f"Digest: {digest}")

    elif kind == "repo_updated":
        name = repo or "a repository"
        paragraphs.append(f"Hippius manifest updated for {name}.")
        if digest := _digest_label(detail):
            paragraphs.append(f"New digest: {digest}")

    elif kind == "reg_fee_low":
        burn = detail.get("registration_burn_tao")
        tier = detail.get("threshold_tao")
        burn_s = f"{float(burn):.4f}" if burn is not None else "unknown"
        tier_s = f"{float(tier):g}" if tier is not None else "unknown"
        paragraphs.append(
            f"Registration burn is {burn_s} τ, below your {tier_s} τ alert level."
        )
        paragraphs.append("Good time to register if you were waiting for lower fees.")

    else:
        paragraphs.append(message[:400])

    return "\n\n".join(paragraphs)


def _primary_url(kind: AlertKind, detail: dict[str, Any], subnet: int | None) -> str | None:
    if kind == "reg_fee_low":
        return taostats_subnet_url(subnet) if subnet is not None else None
    if kind == "crown_lost":
        new_repo = detail.get("new_repo")
        if new_repo:
            return hippius_repo_url(str(new_repo))
    repo = _repo_from_detail(detail)
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
    heading = _title_line(kind, subnet, detail)
    prose = _write_prose(kind, message, detail)
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
