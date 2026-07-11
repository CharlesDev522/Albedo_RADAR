"""Data-driven merge recommendations for SN97 Albedo models."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard
from app.integrations.albedo_scoring_results import fetch_scoring_results_jsonl
from app.schemas.albedo_merge_advisor import (
    AlbedoMergeAdvisorRecommendation,
    AlbedoMergeDonorCandidate,
    AlbedoMergeLayerHint,
    AlbedoMergeMethodOption,
    AlbedoMergeMethodRecommendation,
)
from app.services.albedo_analysis_service import (
    _consensus_pattern,
    _judge_votes,
    parse_model_uri,
)
from app.services.albedo_scoring_analysis_service import (
    CHALLENGER_SIDE,
    KING_SIDE_RAW,
    _binary_eval_runs,
    _scoring_results_url,
)

logger = logging.getLogger(__name__)

_METHOD_PRETTY = {
    "nuslerp": "NuSLERP",
    "ties": "TIES",
    "dare_ties": "DARE TIES",
    "task_arithmetic": "Task Arithmetic",
    "linear": "Linear",
    "slerp": "SLERP",
    "karcher": "Karcher Mean",
    "passthrough": "Passthrough",
}

_MAX_DONORS = 5
_MIN_DONOR_DUELS = 1
_JUDGE_SPREAD_RELIABLE = 0.25
_NARROW_MARGIN = 0.05
_DOMINANT_DONOR_WEIGHT = 0.70


def mergekit_model_ref(model_uri: str | None) -> str:
    """Normalize an Albedo model URI for mergekit YAML."""
    if not model_uri:
        return "unknown"
    uri = model_uri.strip()
    if "://" in uri:
        uri = uri.split("://", 1)[1]
    return uri


def _model_label(model_uri: str, repo: str | None = None) -> str:
    if repo:
        return repo
    _ns, name, _uri = parse_model_uri(model_uri)
    return name or model_uri


def _duel_margin(run: dict[str, Any]) -> float:
    return float(run.get("win_margin") or 0.0)


def _challenger_uri(run: dict[str, Any]) -> str:
    return str(run.get("model_uri") or "")


def _king_uri(run: dict[str, Any]) -> str:
    king = run.get("king") or {}
    return str(king.get("model_uri") or "")


def _judge_reliability(run: dict[str, Any]) -> float:
    votes = _judge_votes(run)
    if not votes:
        return 0.5
    pattern = _consensus_pattern(votes)
    if pattern in ("unanimous_challenger", "unanimous_king"):
        return 1.0
    if pattern in ("split_2_1_challenger", "split_1_2_king"):
        return 0.75
    return 0.4


def _is_consensus_duel(run: dict[str, Any]) -> bool:
    return _judge_reliability(run) >= 0.75


def bradley_terry_strengths(
    outcomes: list[tuple[str, str, float]],
    *,
    iterations: int = 40,
) -> dict[str, float]:
    """Estimate model strengths from weighted pairwise outcomes (winner score 1..0)."""
    models = sorted({a for a, b, _ in outcomes} | {b for a, b, _ in outcomes})
    if not models:
        return {}
    strength = {m: 1.0 for m in models}
    for _ in range(iterations):
        numer = {m: 0.0 for m in models}
        denom = {m: 0.0 for m in models}
        for a, b, score in outcomes:
            sa, sb = strength[a], strength[b]
            denom[a] += sb / (sa + sb + 1e-9)
            denom[b] += sa / (sa + sb + 1e-9)
            numer[a] += score
            numer[b] += 1.0 - score
        for m in models:
            if denom[m] > 0:
                strength[m] = max(1e-6, numer[m] / denom[m])
        avg = mean(strength.values())
        if avg > 0:
            strength = {m: v / avg for m, v in strength.items()}
    return strength


def _collect_duel_outcomes(
    eval_runs: list[dict[str, Any]],
    *,
    base_uri: str,
    consensus_only: bool,
) -> tuple[list[tuple[str, str, float]], int, int]:
    outcomes: list[tuple[str, str, float]] = []
    analyzed = 0
    consensus_count = 0
    for run in eval_runs:
        ch_uri = _challenger_uri(run)
        k_uri = _king_uri(run) or base_uri
        if not ch_uri or not k_uri:
            continue
        analyzed += 1
        reliable = _judge_reliability(run)
        if reliable >= 0.75:
            consensus_count += 1
        if consensus_only and reliable < 0.75:
            continue
        weight = reliable
        margin = _duel_margin(run)
        if bool(run.get("challenger_won")):
            score = 0.5 + min(0.49, abs(margin))
        else:
            score = 0.5 - min(0.49, abs(margin))
        outcomes.append((ch_uri, k_uri, score * weight))
    return outcomes, analyzed, consensus_count


def _donor_stats_from_duels(
    eval_runs: list[dict[str, Any]],
    *,
    base_uri: str,
    coronation_by_uri: dict[str, int],
    reign_slots_by_uri: dict[str, int],
) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "duels": 0,
            "wins": 0,
            "margins": [],
            "reliability": [],
            "repo": None,
        }
    )
    for run in eval_runs:
        ch_uri = _challenger_uri(run)
        if not ch_uri or ch_uri == base_uri:
            continue
        k_uri = _king_uri(run) or base_uri
        if k_uri != base_uri:
            continue
        s = stats[ch_uri]
        s["duels"] += 1
        margin = _duel_margin(run)
        s["margins"].append(margin)
        s["reliability"].append(_judge_reliability(run))
        if bool(run.get("challenger_won")):
            s["wins"] += 1
        ns, name, _ = parse_model_uri(ch_uri)
        s["repo"] = f"{ns}/{name}" if ns else name
    for uri, count in coronation_by_uri.items():
        if uri and uri != base_uri:
            stats[uri]["coronations"] = count
    for uri, slots in reign_slots_by_uri.items():
        if uri and uri != base_uri:
            stats[uri]["reign_slots"] = slots
    return stats


async def _sample_mass_by_uri(
    eval_runs: list[dict[str, Any]],
    *,
    base_uri: str,
    settings: Settings,
    client: httpx.AsyncClient,
    fresh: bool,
    limit: int = 12,
) -> tuple[dict[str, float], int]:
    """Aggregate per-sample challenger win mass from scoring JSONL."""
    binary_runs = _binary_eval_runs(eval_runs)
    binary_runs.sort(key=lambda r: str(r.get("finished_at") or ""), reverse=True)
    mass: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    scanned = 0
    for run in binary_runs[:limit]:
        ch_uri = _challenger_uri(run)
        if not ch_uri or ch_uri == base_uri:
            continue
        url = _scoring_results_url(run)
        if not url:
            continue
        try:
            rows = await fetch_scoring_results_jsonl(
                url, settings=settings, client=client, fresh=fresh
            )
        except Exception:
            logger.warning(
                "merge advisor sample mass skip eval_run_id=%s", run.get("eval_run_id"), exc_info=True
            )
            continue
        scanned += 1
        ch_wins = 0.0
        total = 0.0
        for sample in rows:
            for entry in sample.get("judge_results") or []:
                side = entry.get("side")
                if side not in (CHALLENGER_SIDE, KING_SIDE_RAW):
                    continue
                ans = entry.get("answer")
                if ans is None:
                    continue
                total += 1.0
                if side == CHALLENGER_SIDE and bool(ans):
                    ch_wins += 1.0
                if side == KING_SIDE_RAW and not bool(ans):
                    ch_wins += 1.0
        if total > 0:
            mass[ch_uri] += ch_wins / total
            counts[ch_uri] += 1
    averaged = {
        uri: mass[uri] / counts[uri] for uri in mass if counts[uri] > 0
    }
    return averaged, scanned


def _raw_donor_score(
    *,
    bt_strength: float,
    win_pct: float,
    avg_margin: float | None,
    coronations: int,
    reign_slots: int,
    sample_mass: float | None,
    judge_reliability: float | None,
) -> float:
    margin_bonus = 1.0
    if avg_margin is not None:
        margin_bonus += max(0.0, avg_margin) * 2.0
    reign_bonus = 1.0 + 0.15 * coronations + 0.05 * reign_slots
    sample_factor = 1.0
    if sample_mass is not None:
        sample_factor = 0.5 + sample_mass
    reliability = judge_reliability if judge_reliability is not None else 0.75
    return max(1e-6, bt_strength * (0.5 + win_pct / 100.0) * margin_bonus * reign_bonus * sample_factor * reliability)


def _normalize_weights(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values())
    if total <= 0:
        n = len(scores)
        return {k: 1.0 / n for k in scores} if n else {}
    return {k: v / total for k, v in scores.items()}


def _margin_noise(eval_runs: list[dict[str, Any]], base_uri: str) -> float:
    margins = [
        _duel_margin(r)
        for r in eval_runs
        if _king_uri(r) == base_uri or not _king_uri(r)
    ]
    if len(margins) < 2:
        return 0.0
    return pstdev(margins)


def _select_merge_method(
    *,
    donor_count: int,
    weights: dict[str, float],
    margin_noise: float,
    avg_margin: float | None,
    consensus_ratio: float,
) -> AlbedoMergeMethodRecommendation:
    alternatives: list[AlbedoMergeMethodOption] = []
    if donor_count == 0:
        return AlbedoMergeMethodRecommendation(
            method="passthrough",
            pretty_name=_METHOD_PRETTY["passthrough"],
            parameters={},
            rationale=["No strong donor models found in recent duels against the current king."],
            alternatives=alternatives,
        )

    dominant = max(weights.values()) if weights else 0.0
    narrow = avg_margin is not None and abs(avg_margin) < _NARROW_MARGIN
    noisy = margin_noise > 0.12 or consensus_ratio < 0.5

    candidates: list[tuple[str, float, str]] = []
    if donor_count == 1 or dominant >= _DOMINANT_DONOR_WEIGHT:
        candidates.append(
            (
                "nuslerp",
                0.9 if donor_count == 1 else 0.85,
                "Single strong donor or one dominant weight — interpolate king ↔ donor with NuSLERP task vectors.",
            )
        )
    if donor_count >= 2:
        candidates.append(
            (
                "ties",
                0.8 if not noisy else 0.55,
                "Multiple donors with judge consensus — TIES sparsifies task vectors and resolves sign interference.",
            )
        )
    if donor_count >= 3 or noisy:
        candidates.append(
            (
                "dare_ties",
                0.75 if noisy else 0.6,
                "Noisy judge splits or many donors — DARE random pruning + TIES consensus reduces negative synergy.",
            )
        )
    if narrow:
        candidates.append(
            (
                "task_arithmetic",
                0.7,
                "Margins are tight — small task-vector blend preserves king behavior while borrowing donor edges.",
            )
        )
    if donor_count >= 4:
        candidates.append(
            (
                "karcher",
                0.5,
                "Many peers in weight space — Karcher mean is a geometry-aware average when linear blends fail.",
            )
        )

    candidates.sort(key=lambda c: -c[1])
    method, _score, rationale_line = candidates[0]
    alternatives = [
        AlbedoMergeMethodOption(method=m, score=round(s, 3), rationale=r) for m, s, r in candidates[1:4]
    ]

    params: dict[str, float | bool | str] = {}
    rationale = [rationale_line]
    if method == "nuslerp":
        t = min(0.65, max(0.12, dominant))
        params["t"] = round(t, 3)
        rationale.append(f"NuSLERP t={params['t']}: higher t shifts toward the top donor task vector.")
    elif method in ("ties", "dare_ties"):
        params["lambda"] = 1.0
        params["normalize"] = True
        density = 0.65 if not noisy else 0.45
        params["default_density"] = round(density, 2)
        rationale.append(
            f"Per-donor density≈{params['default_density']}: retain top-magnitude task-vector weights."
        )
        if method == "dare_ties":
            params["rescale"] = True
            rationale.append("DARE rescale enabled to recover pruned mass after random sparsification.")
    elif method == "task_arithmetic":
        params["lambda"] = 0.35 if narrow else 0.6
        params["normalize"] = True
        rationale.append(f"Task arithmetic λ={params['lambda']} keeps the blend conservative on narrow margins.")
    elif method == "karcher":
        params["max_iter"] = 10
        params["tol"] = 1e-5

    return AlbedoMergeMethodRecommendation(
        method=method,
        pretty_name=_METHOD_PRETTY.get(method, method),
        parameters=params,
        rationale=rationale,
        alternatives=alternatives,
    )


def _layer_density_hints(donor_count: int, avg_margin: float | None) -> list[AlbedoMergeLayerHint]:
    if donor_count == 0:
        return []
    base_density = 0.55 if avg_margin is not None and avg_margin > 0.1 else 0.4
    return [
        AlbedoMergeLayerHint(
            layer_fraction_start=0.0,
            layer_fraction_end=0.33,
            density=round(base_density * 0.85, 2),
            note="Early layers: lower density — preserve tokenizer/embed alignment with king.",
        ),
        AlbedoMergeLayerHint(
            layer_fraction_start=0.33,
            layer_fraction_end=0.66,
            density=round(base_density, 2),
            note="Mid layers: balanced task-vector injection.",
        ),
        AlbedoMergeLayerHint(
            layer_fraction_start=0.66,
            layer_fraction_end=1.0,
            density=round(min(0.75, base_density * 1.15), 2),
            note="Late layers: higher density — duel margins often reflect reasoning/style here.",
        ),
    ]


def _yaml_scalar(value: float | bool | str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.6g}"
    return str(value)


def _yaml_dump(doc: dict[str, Any]) -> str:
    lines: list[str] = []

    def emit(key: str, value: Any, indent: int = 0) -> None:
        pad = "  " * indent
        if isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            for sub_key, sub_val in value.items():
                emit(sub_key, sub_val, indent + 1)
        elif isinstance(value, list):
            lines.append(f"{pad}{key}:")
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"{pad}  -")
                    for sub_key, sub_val in item.items():
                        if isinstance(sub_val, dict):
                            lines.append(f"{pad}    {sub_key}:")
                            for inner_k, inner_v in sub_val.items():
                                lines.append(f"{pad}      {inner_k}: {_yaml_scalar(inner_v)}")
                        else:
                            lines.append(f"{pad}    {sub_key}: {_yaml_scalar(sub_val)}")
                else:
                    lines.append(f"{pad}  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{pad}{key}: {_yaml_scalar(value)}")

    for key, value in doc.items():
        emit(key, value, 0)
    return "\n".join(lines) + "\n"


def _build_mergekit_yaml(
    *,
    method: str,
    base_ref: str,
    donors: list[AlbedoMergeDonorCandidate],
    parameters: dict[str, float | bool | str],
    layer_hints: list[AlbedoMergeLayerHint],
) -> str:
    if method == "passthrough":
        doc = {
            "merge_method": "passthrough",
            "dtype": "bfloat16",
            "models": [{"model": base_ref}],
        }
        return _yaml_dump(doc)

    doc: dict[str, Any] = {
        "merge_method": method,
        "base_model": base_ref,
        "dtype": "bfloat16",
    }
    if parameters:
        global_params = {
            k: v for k, v in parameters.items() if k not in ("default_density",)
        }
        if global_params:
            doc["parameters"] = global_params

    default_density = parameters.get("default_density")
    models: list[dict[str, Any]] = [{"model": base_ref}]
    if method == "nuslerp":
        top = donors[0] if donors else None
        if top:
            models.append({"model": top.mergekit_ref})
    else:
        for donor in donors:
            entry: dict[str, Any] = {
                "model": donor.mergekit_ref,
                "parameters": {"weight": round(donor.merge_weight, 4)},
            }
            if default_density is not None:
                density = donor.density if donor.density is not None else float(default_density)
                entry["parameters"]["density"] = round(density, 3)
            models.append(entry)
    doc["models"] = models

    yaml_text = _yaml_dump(doc)
    if layer_hints:
        hint_lines = ["# Suggested per-layer density gradient (manual mergekit slices):"]
        for hint in layer_hints:
            hint_lines.append(
                f"#  layers {hint.layer_fraction_start:.0%}-{hint.layer_fraction_end:.0%}: "
                f"density={hint.density} — {hint.note}"
            )
        yaml_text = "\n".join(hint_lines) + "\n" + yaml_text
    return yaml_text


def build_merge_advisor_recommendation(
    dashboard: dict[str, Any],
    *,
    subnet: int = 97,
    sample_mass_by_uri: dict[str, float] | None = None,
    sample_mass_duels: int = 0,
    max_donors: int = _MAX_DONORS,
    consensus_only: bool = False,
) -> AlbedoMergeAdvisorRecommendation:
    reign_members = (dashboard.get("reign") or {}).get("members") or []
    base_uri = ""
    base_repo = None
    if reign_members:
        base_uri = str(reign_members[0].get("model_uri") or "")
        ns, name, _ = parse_model_uri(base_uri)
        base_repo = f"{ns}/{name}" if ns else name

    eval_runs = list(dashboard.get("eval_runs") or [])
    coronation_by_uri: dict[str, int] = defaultdict(int)
    for run in eval_runs:
        if run.get("coronated"):
            coronation_by_uri[_challenger_uri(run)] += 1
    reign_slots_by_uri: dict[str, int] = defaultdict(int)
    for member in reign_members:
        uri = str(member.get("model_uri") or "")
        if uri:
            reign_slots_by_uri[uri] += 1

    outcomes, duels_analyzed, consensus_duels = _collect_duel_outcomes(
        eval_runs, base_uri=base_uri, consensus_only=consensus_only
    )
    bt = bradley_terry_strengths(outcomes)
    donor_raw = _donor_stats_from_duels(
        eval_runs,
        base_uri=base_uri,
        coronation_by_uri=dict(coronation_by_uri),
        reign_slots_by_uri=dict(reign_slots_by_uri),
    )

    scored: list[tuple[str, float, dict[str, Any]]] = []
    for uri, s in donor_raw.items():
        if s["duels"] < _MIN_DONOR_DUELS:
            continue
        win_pct = (s["wins"] / s["duels"] * 100.0) if s["duels"] else 0.0
        avg_margin = mean(s["margins"]) if s["margins"] else None
        judge_rel = mean(s["reliability"]) if s["reliability"] else None
        sample_mass = (sample_mass_by_uri or {}).get(uri)
        bt_strength = bt.get(uri, 1.0)
        raw = _raw_donor_score(
            bt_strength=bt_strength,
            win_pct=win_pct,
            avg_margin=avg_margin,
            coronations=int(s.get("coronations") or 0),
            reign_slots=int(s.get("reign_slots") or 0),
            sample_mass=sample_mass,
            judge_reliability=judge_rel,
        )
        scored.append((uri, raw, {**s, "win_pct": win_pct, "avg_margin": avg_margin, "judge_rel": judge_rel, "bt": bt_strength, "sample_mass": sample_mass}))

    scored.sort(key=lambda row: -row[1])
    top = scored[:max_donors]
    weight_scores = {uri: raw for uri, raw, _ in top}
    norm_weights = _normalize_weights(weight_scores)

    donors: list[AlbedoMergeDonorCandidate] = []
    for uri, raw, meta in top:
        duels = int(meta["duels"])
        wins = int(meta["wins"])
        avg_m = meta.get("avg_margin")
        density = None
        if avg_m is not None:
            density = round(min(0.8, max(0.25, 0.4 + abs(float(avg_m)))), 3)
        donors.append(
            AlbedoMergeDonorCandidate(
                model_uri=uri,
                repo=meta.get("repo"),
                label=_model_label(uri, meta.get("repo")),
                mergekit_ref=mergekit_model_ref(uri),
                duels=duels,
                wins=wins,
                losses=duels - wins,
                win_pct=round(float(meta["win_pct"]), 1),
                avg_margin=round(float(avg_m), 4) if avg_m is not None else None,
                bt_strength=round(float(meta["bt"]), 4),
                coronations=int(meta.get("coronations") or 0),
                reign_slots=int(meta.get("reign_slots") or 0),
                sample_mass=round(float(meta["sample_mass"]), 4) if meta.get("sample_mass") is not None else None,
                judge_reliability=round(float(meta["judge_rel"]), 3) if meta.get("judge_rel") is not None else None,
                merge_weight=round(norm_weights.get(uri, 0.0), 4),
                density=density,
            )
        )

    margins_vs_king = [
        _duel_margin(r)
        for r in eval_runs
        if _challenger_uri(r) and (_king_uri(r) == base_uri or not _king_uri(r))
    ]
    avg_margin = mean(margins_vs_king) if margins_vs_king else None
    margin_noise = _margin_noise(eval_runs, base_uri)
    consensus_ratio = consensus_duels / duels_analyzed if duels_analyzed else 0.0

    method = _select_merge_method(
        donor_count=len(donors),
        weights=norm_weights,
        margin_noise=margin_noise,
        avg_margin=avg_margin,
        consensus_ratio=consensus_ratio,
    )
    layer_hints = _layer_density_hints(len(donors), avg_margin)

    data_sources = ["dashboard.json eval_runs", "reign chain (base model)"]
    if consensus_only:
        data_sources.append("judge-consensus duel filter")
    if sample_mass_by_uri:
        data_sources.append(f"SCORING_RESULTS sample mass ({sample_mass_duels} duels)")

    rationale = [
        f"Base model: current king {_model_label(base_uri, base_repo)}.",
        f"Analyzed {duels_analyzed} duels ({consensus_duels} high-consensus).",
    ]
    if donors:
        top_donor = donors[0]
        rationale.append(
            f"Top donor {top_donor.label}: {top_donor.win_pct:.1f}% win rate over {top_donor.duels} duels, "
            f"BT strength {top_donor.bt_strength:.2f}, merge weight {top_donor.merge_weight:.2f}."
        )
    if sample_mass_by_uri:
        rationale.append("Sample-level SCORING_RESULTS mass refines donor weights toward per-question wins.")
    rationale.extend(method.rationale)

    binary_duels = len(_binary_eval_runs(eval_runs))
    yaml_text = _build_mergekit_yaml(
        method=method.method,
        base_ref=mergekit_model_ref(base_uri),
        donors=donors,
        parameters=method.parameters,
        layer_hints=layer_hints,
    )

    return AlbedoMergeAdvisorRecommendation(
        subnet=subnet,
        generated_at=datetime.now(timezone.utc).isoformat(),
        base_model_uri=base_uri,
        base_repo=base_repo,
        base_mergekit_ref=mergekit_model_ref(base_uri),
        base_label=_model_label(base_uri, base_repo),
        donors=donors,
        method=method,
        layer_hints=layer_hints,
        mergekit_yaml=yaml_text,
        rationale=rationale,
        data_sources=data_sources,
        duels_analyzed=duels_analyzed,
        binary_duels_analyzed=binary_duels,
        sample_mass_duels=sample_mass_duels,
        judge_consensus_duels=consensus_duels,
        note=(
            "Recommendation uses duel outcomes, Bradley–Terry strengths, reign/coronation bonuses, "
            "and optional per-sample scoring mass. Validate merged checkpoints in real Albedo duels."
        ),
    )


async def get_merge_advisor_recommendation(
    *,
    subnet: int = 97,
    settings: Settings | None = None,
    fresh: bool = False,
    include_sample_mass: bool = True,
    max_donors: int = _MAX_DONORS,
    consensus_only: bool = False,
) -> AlbedoMergeAdvisorRecommendation:
    settings = settings or get_settings()
    dashboard = await fetch_dashboard(settings=settings)
    sample_mass: dict[str, float] | None = None
    sample_mass_duels = 0
    if include_sample_mass:
        eval_runs = list(dashboard.get("eval_runs") or [])
        reign = (dashboard.get("reign") or {}).get("members") or []
        base_uri = str(reign[0].get("model_uri") or "") if reign else ""
        async with httpx.AsyncClient(timeout=max(settings.market_http_timeout_seconds, 30.0)) as client:
            sample_mass, sample_mass_duels = await _sample_mass_by_uri(
                eval_runs,
                base_uri=base_uri,
                settings=settings,
                client=client,
                fresh=fresh,
            )
    return build_merge_advisor_recommendation(
        dashboard,
        subnet=subnet,
        sample_mass_by_uri=sample_mass,
        sample_mass_duels=sample_mass_duels,
        max_donors=max_donors,
        consensus_only=consensus_only,
    )
