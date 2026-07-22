"""Correct Bittensor / Albedo wording for Slack and alert records."""

from __future__ import annotations

from typing import Any

from app.notifications.kinds import AlertKind


def repo_from_detail(detail: dict[str, Any]) -> str | None:
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


def uid_from_detail(detail: dict[str, Any]) -> int | None:
    uid = detail.get("uid")
    return int(uid) if uid is not None else None


def pipe_version(detail: dict[str, Any]) -> str | None:
    raw = detail.get("version") or detail.get("commitment_type")
    if not raw:
        return None
    text = str(raw).lower()
    if text in ("v6", "v7"):
        return text
    return None


def miner_ref(detail: dict[str, Any], repo: str | None = None) -> str:
    repo = repo or repo_from_detail(detail) or "unknown model"
    uid = uid_from_detail(detail)
    if uid is not None:
        return f"UID {uid} ({repo})"
    return repo


def digest_short(detail: dict[str, Any]) -> str | None:
    raw = detail.get("digest") or detail.get("hub_digest")
    if not raw:
        return None
    text = str(raw).replace("sha256:", "")
    if len(text) > 20:
        return f"sha256:{text[:20]}…"
    return f"sha256:{text}"


def title_for(kind: AlertKind, subnet: int | None, detail: dict[str, Any]) -> str:
    uid = uid_from_detail(detail)
    repo = repo_from_detail(detail)
    sn = f"SN{subnet}" if subnet is not None else "subnet"
    pipe = pipe_version(detail)

    if kind == "duel_new":
        return f"Albedo eval started — UID {uid} vs king" if uid is not None else f"Albedo eval started on {sn}"

    if kind == "crown_won":
        return f"UID {uid} coronated as king" if uid is not None else "New king coronated"

    if kind == "king_defended":
        return f"King defended — UID {uid} lost eval" if uid is not None else "King defended the reign"

    if kind == "crown_lost":
        prev = detail.get("previous_king_version")
        return f"King v{prev} dethroned on {sn}" if prev is not None else f"King dethroned on {sn}"

    if kind == "commit_new":
        if uid is not None and repo:
            return f"UID {uid} revealed {pipe or 'pipe'} commitment — {repo}"
        if uid is not None:
            return f"UID {uid} revealed model commitment on {sn}"
        return f"Model commitment revealed on {sn}"

    if kind == "commit_updated":
        if uid is not None and repo:
            return f"UID {uid} changed CommitmentOf — {repo}"
        if uid is not None:
            return f"UID {uid} changed on-chain model commitment"
        return f"CommitmentOf changed on {sn}"

    if kind in ("slot_new", "slot_changed"):
        pipe_s = f" {pipe}" if pipe else ""
        return (
            f"UID {uid} published{pipe_s} commitment on {sn}"
            if uid is not None
            else f"UID published pipe commitment on {sn}"
        )

    if kind == "repo_new":
        host = detail.get("host") or (detail.get("meta") or {}).get("host")
        hub = "Hugging Face" if host == "huggingface" else "Hippius"
        return f"New {hub} repo: {repo}" if repo else f"New {hub} repo on {sn}"

    if kind == "repo_updated":
        return f"Hippius manifest updated: {repo}" if repo else f"Hippius manifest updated on {sn}"

    if kind == "reg_fee_low":
        tier = detail.get("threshold_tao")
        tier_s = f"{float(tier):g} τ" if tier is not None else "alert level"
        return f"{sn} registration burn below {tier_s}"

    if kind == "eval_dq":
        uid = uid_from_detail(detail)
        code = detail.get("fault_code")
        if uid is not None and code:
            return f"UID {uid} disqualified — {code}"
        if uid is not None:
            return f"UID {uid} added to eval DQ list"
        return f"Miner added to eval DQ list on {sn}"

    if kind == "eval_queue_entered":
        uid = uid_from_detail(detail)
        state = detail.get("state")
        state_label = {
            "SUBMITTED": "queued for Hippius validation",
            "HIPPIUS_RETRYABLE": "queued for Hippius validation (retryable)",
            "HIPPIUS_RUNNING": "Hippius validation running",
        }.get(state or "", "entered validation pipeline")
        if uid is not None:
            return f"UID {uid} {state_label}"
        return f"Model {state_label} on {sn}"

    return f"Alert on {sn}"


def prose_for(kind: AlertKind, message: str, detail: dict[str, Any]) -> str:
    repo = repo_from_detail(detail)
    king_repo = detail.get("king_repo")
    pipe = pipe_version(detail)
    paragraphs: list[str] = []

    if kind == "duel_new":
        challenger = miner_ref(detail, repo)
        king_v = detail.get("king_version")
        if king_repo and king_v is not None:
            opponent = f"reigning king {king_repo} (king v{king_v})"
        elif king_v is not None:
            opponent = f"reigning king (v{king_v})"
        else:
            opponent = "the reigning king"
        paragraphs.append(
            f"{challenger} entered an Albedo evaluation duel against {opponent}."
        )
        state = detail.get("state")
        samples = detail.get("sample_count")
        if state and samples is not None:
            paragraphs.append(f"Eval phase: {state}. Sample batch size: {samples}.")
        elif state:
            paragraphs.append(f"Eval phase: {state}.")
        elif samples is not None:
            paragraphs.append(f"Sample batch size: {samples}.")

    elif kind == "crown_won":
        winner = miner_ref(detail, repo)
        king_v = detail.get("king_version")
        defeated_v = detail.get("defeated_king_version")
        if king_v is not None and defeated_v is not None:
            paragraphs.append(
                f"{winner} won the eval and was coronated as king v{king_v}, "
                f"replacing king v{defeated_v}."
            )
        elif king_v is not None:
            paragraphs.append(f"{winner} won the eval and was coronated as king v{king_v}.")
        else:
            paragraphs.append(f"{winner} won the eval and took the crown.")
        if line := _score_line(detail):
            paragraphs.append(line)

    elif kind == "king_defended":
        challenger = miner_ref(detail, repo)
        king_v = detail.get("king_version")
        king_name = king_repo or "the reigning king"
        if king_v is not None:
            paragraphs.append(
                f"{challenger} lost the Albedo eval against {king_name} (king v{king_v}). "
                f"The king keeps the reign."
            )
        else:
            paragraphs.append(
                f"{challenger} lost the Albedo eval. The reigning king keeps the crown."
            )
        if line := _score_line(detail):
            paragraphs.append(line)

    elif kind == "crown_lost":
        prev_v = detail.get("previous_king_version")
        new_v = detail.get("new_king_version")
        new_repo = detail.get("new_repo") or "unknown model"
        paragraphs.append(
            f"King v{prev_v} is no longer reigning. "
            f"The active king is now v{new_v}: {new_repo}."
        )

    elif kind == "commit_new":
        who = miner_ref(detail, repo)
        block = detail.get("commit_block")
        version_s = f"{pipe} " if pipe else ""
        block_s = f" at block {block}" if block is not None else ""
        paragraphs.append(
            f"{who} revealed a new {version_s}pipe CommitmentOf on {block_s}. "
            f"This publishes the miner's model URI on-chain for validators to verify."
        )
        if digest := digest_short(detail):
            paragraphs.append(f"Model digest: {digest}")

    elif kind == "commit_updated":
        who = miner_ref(detail, repo)
        block = detail.get("commit_block")
        block_s = f" at block {block}" if block is not None else ""
        paragraphs.append(
            f"{who} changed their CommitmentOf{block_s}. "
            f"The revealed model URI or digest on-chain is different from before."
        )
        if digest := digest_short(detail):
            paragraphs.append(f"New model digest: {digest}")

    elif kind in ("slot_new", "slot_changed"):
        who = f"UID {uid_from_detail(detail)}" if uid_from_detail(detail) is not None else "A UID"
        model = detail.get("detail") or repo or "a model"
        pipe_s = pipe or "pipe"
        block = detail.get("commit_block")
        block_s = f" at block {block}" if block is not None else ""
        if kind == "slot_changed":
            paragraphs.append(
                f"{who} published a new {pipe_s} Albedo commitment{block_s} for {model} "
                f"(slot commitment changed on an existing metagraph UID)."
            )
        else:
            paragraphs.append(
                f"{who} on the metagraph had no published commitment before. "
                f"It now reveals a {pipe_s} Albedo commitment{block_s} for {model}."
            )

    elif kind == "eval_dq":
        who = miner_ref(detail, repo)
        fault_class = detail.get("fault_class") or "UNKNOWN"
        fault_code = detail.get("fault_code") or "unknown"
        paragraphs.append(
            f"{who} was added to the Albedo eval DQ (disqualified) list after a terminal "
            f"pipeline failure ({fault_class}: {fault_code})."
        )
        if fault_msg := detail.get("fault_message"):
            paragraphs.append(str(fault_msg))

    elif kind == "eval_queue_entered":
        who = miner_ref(detail, repo)
        state = detail.get("state") or "unknown"
        state_label = {
            "SUBMITTED": "queued for Hippius validation",
            "HIPPIUS_RETRYABLE": "queued for Hippius validation (retryable)",
            "HIPPIUS_RUNNING": "running Hippius validation",
        }.get(state, state.replace("_", " ").lower())
        paragraphs.append(
            f"{who} entered the Albedo eval pipeline — {state_label}."
        )
        if submission_id := detail.get("submission_id"):
            paragraphs.append(f"Submission: {submission_id}.")

    elif kind == "repo_new":
        name = repo or "a repository"
        fam = detail.get("model_family")
        fam_s = f" ({fam})" if fam else ""
        host = detail.get("host") or (detail.get("meta") or {}).get("host")
        hub = "Hugging Face" if host == "huggingface" else "Hippius"
        paragraphs.append(
            f"A new model repo appeared on {hub}: {name}{fam_s}. "
            f"This is the off-chain manifest validators pull during eval."
        )
        if digest := digest_short(detail):
            paragraphs.append(f"Hub digest: {digest}")

    elif kind == "repo_updated":
        name = repo or "a repository"
        paragraphs.append(
            f"The Hippius hub manifest for {name} changed "
            f"(new files or digest on the hub — separate from on-chain CommitmentOf)."
        )
        if digest := digest_short(detail):
            paragraphs.append(f"New hub digest: {digest}")

    elif kind == "reg_fee_low":
        burn = detail.get("registration_burn_tao")
        tier = detail.get("threshold_tao")
        burn_s = f"{float(burn):.4f}" if burn is not None else "unknown"
        tier_s = f"{float(tier):g}" if tier is not None else "unknown"
        paragraphs.append(
            f"Subnet registration burn is {burn_s} τ, below your {tier_s} τ alert threshold. "
            f"This is the TAO cost to register a new neuron UID on the subnet."
        )

    else:
        paragraphs.append(message[:400])

    return "\n\n".join(paragraphs)


def _pct_score(score: float | None) -> str:
    if score is None:
        return "—"
    return f"{float(score) * 100:.1f}%"


def _score_line(detail: dict[str, Any]) -> str | None:
    ch = detail.get("score_challenger")
    kg = detail.get("score_king")
    margin = detail.get("win_margin")
    judge_scores = detail.get("judge_scores") or []
    if ch is None and kg is None and not judge_scores:
        return None

    parts: list[str] = []
    if ch is not None or kg is not None:
        parts.append(f"*Total:* challenger {_pct_score(ch)} · king {_pct_score(kg)}")
        if margin is not None:
            m = float(margin)
            if m > 0:
                parts.append(f"Challenger ahead by {_pct_score(m)}.")
            elif m < 0:
                parts.append(f"King ahead by {_pct_score(abs(m))}.")
            else:
                parts.append("Scores tied.")

    if judge_scores:
        judge_lines: list[str] = []
        for row in judge_scores:
            if not isinstance(row, dict):
                continue
            judge = row.get("judge") or "judge"
            pick = "ch" if row.get("pick_challenger") else "k"
            judge_lines.append(
                f"• *{judge}:* ch {_pct_score(row.get('challenger_score'))} "
                f"vs k {_pct_score(row.get('king_score'))} → {pick}"
            )
        if judge_lines:
            parts.append("*Judges:*\n" + "\n".join(judge_lines))

    return "\n".join(parts)
