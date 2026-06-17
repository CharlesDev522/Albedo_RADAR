"""Normalize Albedo dashboard v2 (data/dashboard.json) and build HF-account analytics."""

from __future__ import annotations

import re
from typing import Any

_ROMAN = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def king_title_name(reign_number: int | None) -> str:
    n = int(reign_number) if reign_number is not None else 0
    if n <= 0:
        return "BASE MODEL"
    num = n
    parts: list[str] = []
    for value, numeral in _ROMAN:
        while num >= value:
            parts.append(numeral)
            num -= value
    return f"ALBEDO-{''.join(parts)}" if parts else "BASE MODEL"


def model_repo(uri: str | None) -> str:
    if not uri:
        return ""
    s = re.sub(r"^[a-z][a-z0-9+.-]*://", "", uri, flags=re.I)
    s = re.sub(r"@[^/]*$", "", s)
    i = s.find("/")
    if i > 0 and "." in s[:i]:
        s = s[i + 1 :]
    return s


def hf_account(uri: str | None) -> str | None:
    repo = model_repo(uri)
    if not repo or "/" not in repo:
        return None
    return repo.split("/", 1)[0]


def verdict_info(run: dict[str, Any]) -> dict[str, Any]:
    won = run.get("challenger_won") is True
    coronated = run.get("coronated") is True
    if coronated:
        badge = "crowned"
    elif won:
        badge = "won"
    else:
        badge = "lost"
    return {
        "won": won,
        "coronated": coronated,
        "badge": badge,
        "score_challenger": run.get("score_challenger"),
        "score_king": run.get("score_king"),
        "win_margin": run.get("win_margin"),
    }


def normalize_dashboard(raw: dict[str, Any]) -> dict[str, Any]:
    """Match official albedo/js/data.js normalize()."""
    runs = raw.get("eval_runs") or []
    return {
        "updated_at": raw.get("updated_at"),
        "chain": raw.get("chain") or {},
        "stats": raw.get("stats") or {},
        "reign": raw.get("reign") or {"members": []},
        "current_eval": raw.get("current_eval"),
        "queue": raw.get("queue") or [],
        "eval_runs": runs,
        "fails": raw.get("fails") or [],
        "crownings": _crownings(runs),
        "schema_version": 2,
    }


def _crownings(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in runs:
        if not r.get("coronated"):
            continue
        out.append(
            {
                "king_version": r.get("king_version"),
                "score_challenger": r.get("score_challenger"),
                "score_king": r.get("score_king"),
                "eval_run_id": r.get("eval_run_id"),
                "finished_at": r.get("finished_at"),
                "model_uri": r.get("model_uri"),
                "uid": r.get("uid"),
                "hotkey": r.get("hotkey"),
                "hf_account": hf_account(r.get("model_uri")),
            }
        )
    out.sort(key=lambda x: int(x.get("king_version") or 0))
    return out


def current_king(reign: dict[str, Any]) -> dict[str, Any] | None:
    members = reign.get("members") or []
    if not members:
        return None
    best = max(members, key=lambda m: int(m.get("king_version") or 0))
    return best


def build_hf_analytics(
    normalized: dict[str, Any],
    *,
    coldkey_by_hotkey: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Per Hippius HF namespace: crowns, dethrones, duel rates."""
    coldkey_by_hotkey = coldkey_by_hotkey or {}
    accounts: dict[str, dict[str, Any]] = {}

    def bucket(name: str | None) -> dict[str, Any]:
        key = name or "unknown"
        if key not in accounts:
            accounts[key] = {
                "hf_account": key,
                "coldkeys": set(),
                "hotkeys": set(),
                "challenges": 0,
                "duel_wins": 0,
                "duel_losses": 0,
                "crowns": 0,
                "dethrones_caused": 0,
                "times_dethroned": 0,
                "reign_versions": [],
                "margins_won": [],
            }
        return accounts[key]

    for run in normalized.get("eval_runs") or []:
        acct = hf_account(run.get("model_uri")) or "unknown"
        b = bucket(acct)
        b["challenges"] += 1
        hk = run.get("hotkey")
        if hk:
            b["hotkeys"].add(str(hk))
            ck = coldkey_by_hotkey.get(str(hk))
            if ck:
                b["coldkeys"].add(ck)
        v = verdict_info(run)
        if v["won"]:
            b["duel_wins"] += 1
            margin = run.get("win_margin")
            if margin is not None:
                b["margins_won"].append(float(margin))
        else:
            b["duel_losses"] += 1
        if v["coronated"]:
            b["crowns"] += 1
            b["dethrones_caused"] += 1
            kv = run.get("king_version")
            if kv is not None:
                b["reign_versions"].append(int(kv))
            defeated = run.get("king") or {}
            defeated_acct = hf_account(defeated.get("model_uri"))
            if defeated_acct:
                bucket(defeated_acct)["times_dethroned"] += 1

    reign_members = normalized.get("reign", {}).get("members") or []
    for m in reign_members:
        acct = hf_account(m.get("model_uri"))
        if not acct:
            continue
        b = bucket(acct)
        hk = m.get("hotkey")
        if hk:
            b["hotkeys"].add(str(hk))
            ck = coldkey_by_hotkey.get(str(hk))
            if ck:
                b["coldkeys"].add(ck)
        kv = m.get("king_version")
        if kv is not None and int(kv) not in b["reign_versions"]:
            b["reign_versions"].append(int(kv))

    rows: list[dict[str, Any]] = []
    for b in accounts.values():
        ch = b["challenges"]
        wins = b["duel_wins"]
        crowns = b["crowns"]
        dethroned = b["times_dethroned"]
        caused = b["dethrones_caused"]
        margins = b["margins_won"]
        rows.append(
            {
                "hf_account": b["hf_account"],
                "coldkeys": sorted(b["coldkeys"]),
                "hotkey_count": len(b["hotkeys"]),
                "challenges": ch,
                "duel_wins": wins,
                "duel_losses": b["duel_losses"],
                "crowns": crowns,
                "dethrones_caused": caused,
                "times_dethroned": dethroned,
                "reign_versions": sorted(set(b["reign_versions"])),
                "win_rate": round(wins / ch, 4) if ch else 0.0,
                "crown_rate": round(crowns / ch, 4) if ch else 0.0,
                "dethrone_rate": round(dethroned / max(dethroned + crowns, 1), 4),
                "avg_win_margin": round(sum(margins) / len(margins), 4) if margins else None,
            }
        )

    rows.sort(
        key=lambda r: (
            -r["crowns"],
            -r["dethrones_caused"],
            -r["duel_wins"],
            -r["challenges"],
        )
    )

    total_crowns = sum(r["crowns"] for r in rows)
    return {
        "accounts": rows,
        "total_eval_runs": len(normalized.get("eval_runs") or []),
        "total_crownings": len(normalized.get("crownings") or []),
        "unique_hf_accounts": len(rows),
        "top_crown_holder": rows[0]["hf_account"] if rows else None,
        "crown_share_top": round(rows[0]["crowns"] / total_crowns, 4) if rows and total_crowns else 0.0,
    }
