"""Data-driven merge recommendations for SN97 Albedo models."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any

from app.config import Settings, get_settings
from app.integrations.albedo_dashboard import fetch_dashboard
from app.chain_reader.albedo_model_family import infer_albedo_model_family
from app.schemas.albedo_merge_advisor import (
    AlbedoMergeAdvisorRecommendation,
    AlbedoMergeDonorCandidate,
    AlbedoMergeGlobalBtRow,
    AlbedoMergeLayerHint,
    AlbedoMergeMethodOption,
    AlbedoMergeMethodRecommendation,
    AlbedoMergeMethodYaml,
    MergeAdvisorMode,
)
from app.services.albedo_analysis_service import (
    _consensus_pattern,
    _judge_votes,
    parse_model_uri,
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
_DEFAULT_MIN_DONOR_DUELS = 2
_RECENT_DUELS_LIMIT = 60
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


def _recent_eval_runs(eval_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs = list(eval_runs)
    runs.sort(key=lambda r: str(r.get("finished_at") or ""), reverse=True)
    return runs[:_RECENT_DUELS_LIMIT]


def _scoring_results_url(eval_run: dict[str, Any]) -> str | None:
    artifacts = eval_run.get("artifacts") or {}
    url = artifacts.get("SCORING_RESULTS") or artifacts.get("scoring_results")
    return str(url) if url else None


def _binary_eval_runs(eval_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        run
        for run in eval_runs
        if run.get("scoring_mode") == "binary" and _scoring_results_url(run)
    ]


def _coronations_from_eval_runs(eval_runs: list[dict[str, Any]]) -> list[Any]:
    from app.services.albedo_king_history import coronation_from_eval_run

    coronations = []
    for run in eval_runs:
        cor = coronation_from_eval_run(run, None)
        if cor:
            coronations.append(cor)
    return sorted(coronations, key=lambda c: c.king_version)


def _king_reign_windows(
    coronations: list[Any],
) -> dict[int, tuple[str, str | None]]:
    sorted_asc = sorted(coronations, key=lambda c: c.king_version)
    windows: dict[int, tuple[str, str | None]] = {}
    for idx, cor in enumerate(sorted_asc):
        active_until = sorted_asc[idx + 1].finished_at if idx + 1 < len(sorted_asc) else None
        windows[cor.king_version] = (cor.finished_at, active_until)
    return windows


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


def _model_family(model_uri: str, repo: str | None = None) -> str | None:
    if repo:
        return infer_albedo_model_family(repo)
    ns, name, _ = parse_model_uri(model_uri)
    repo_guess = f"{ns}/{name}" if ns else name
    return infer_albedo_model_family(repo_guess)


def _architecture_warnings(
    base_family: str | None,
    donors: list[AlbedoMergeDonorCandidate],
) -> list[str]:
    warnings: list[str] = []
    if not base_family:
        warnings.append("Could not infer base model family — verify all donors share architecture before merging.")
        return warnings
    mismatched = [d for d in donors if d.model_family and d.model_family != base_family]
    unknown = [d for d in donors if not d.model_family]
    if mismatched:
        labels = ", ".join(short_label(d.label) for d in mismatched[:4])
        warnings.append(
            f"Family mismatch: base is {base_family} but donor(s) differ ({labels}). "
            "mergekit will likely fail across families."
        )
    if unknown:
        warnings.append(
            f"{len(unknown)} donor(s) have unknown family — confirm they match {base_family}."
        )
    return warnings


def short_label(label: str, max_len: int = 24) -> str:
    return label if len(label) <= max_len else label[: max_len - 1] + "…"


def _global_bt_leaderboard(
    bt: dict[str, float],
    *,
    base_uri: str,
    limit: int = 12,
) -> list[AlbedoMergeGlobalBtRow]:
    ranked = sorted(
        ((uri, strength) for uri, strength in bt.items() if uri and uri != base_uri),
        key=lambda row: -row[1],
    )[:limit]
    rows: list[AlbedoMergeGlobalBtRow] = []
    for idx, (uri, strength) in enumerate(ranked, start=1):
        ns, name, _ = parse_model_uri(uri)
        repo = f"{ns}/{name}" if ns else name
        rows.append(
            AlbedoMergeGlobalBtRow(
                rank=idx,
                model_uri=uri,
                repo=repo,
                label=_model_label(uri, repo),
                bt_strength=round(strength, 4),
            )
        )
    return rows


def _empty_donor_stat() -> dict[str, Any]:
    return {
        "duels": 0,
        "wins": 0,
        "historical_duels": 0,
        "margins": [],
        "reliability": [],
        "repo": None,
        "sources": set(),
        "coronations": 0,
        "reign_slots": 0,
    }


def _touch_donor_stat(
    stats: dict[str, dict[str, Any]],
    uri: str,
    run: dict[str, Any],
    *,
    source: str,
    historical: bool,
) -> None:
    if not uri:
        return
    s = stats[uri]
    s["duels"] += 1
    if historical:
        s["historical_duels"] += 1
    margin = _duel_margin(run)
    s["margins"].append(margin)
    s["reliability"].append(_judge_reliability(run))
    if bool(run.get("challenger_won")):
        s["wins"] += 1
    ns, name, _ = parse_model_uri(uri)
    s["repo"] = f"{ns}/{name}" if ns else name
    s["sources"].add(source)


def _collect_donor_stats(
    eval_runs: list[dict[str, Any]],
    *,
    base_uri: str,
    mode: MergeAdvisorMode,
    king_versions: list[int] | None,
    include_past_kings: bool,
    coronation_by_uri: dict[str, int],
    reign_slots_by_uri: dict[str, int],
    coronations: list[Any],
) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = defaultdict(_empty_donor_stat)

    for run in eval_runs:
        ch_uri = _challenger_uri(run)
        if not ch_uri or ch_uri == base_uri:
            continue
        k_uri = _king_uri(run) or base_uri
        if mode == "current_king":
            if k_uri != base_uri:
                continue
            _touch_donor_stat(stats, ch_uri, run, source="vs_current_king", historical=False)
        else:
            if k_uri == base_uri:
                _touch_donor_stat(stats, ch_uri, run, source="vs_current_king", historical=False)

    if mode == "multi_king":
        windows = _king_reign_windows(coronations)
        versions = king_versions or sorted(windows.keys())
        for king_version in versions:
            if king_version not in windows:
                continue
            coronation_at, active_until = windows[king_version]
            for run in eval_runs:
                king = run.get("king") or {}
                if king.get("king_version") != king_version:
                    continue
                finished = str(run.get("finished_at") or "")
                if finished < coronation_at:
                    continue
                if active_until and finished > active_until:
                    continue
                ch_uri = _challenger_uri(run)
                if not ch_uri or ch_uri == base_uri:
                    continue
                _touch_donor_stat(
                    stats,
                    ch_uri,
                    run,
                    source=f"king_v{king_version}_reign",
                    historical=(_king_uri(run) or "") != base_uri,
                )

        if include_past_kings:
            for cor in coronations:
                uri = str(getattr(cor, "model_uri", "") or "")
                if uri and uri != base_uri:
                    stats[uri]["sources"].add("past_king")
                    stats[uri]["coronations"] = max(int(stats[uri].get("coronations") or 0), 1)

    for uri, count in coronation_by_uri.items():
        if uri and uri != base_uri:
            stats[uri]["coronations"] = count
    for uri, slots in reign_slots_by_uri.items():
        if uri and uri != base_uri:
            stats[uri]["reign_slots"] = slots

    return stats


def _donor_eligible(
    stats: dict[str, Any],
    *,
    min_duels: int,
    include_past_kings: bool,
    mode: MergeAdvisorMode,
) -> bool:
    total_duels = int(stats["duels"])
    if total_duels >= min_duels:
        return True
    if mode == "multi_king" and include_past_kings:
        if int(stats.get("coronations") or 0) > 0 and "past_king" in stats.get("sources", set()):
            return True
        if int(stats.get("coronations") or 0) > 0 and total_duels >= 1:
            return True
    return False


def _raw_donor_score(
    *,
    bt_strength: float,
    win_pct: float,
    avg_margin: float | None,
    coronations: int,
    reign_slots: int,
    judge_reliability: float | None,
) -> float:
    margin_bonus = 1.0
    if avg_margin is not None:
        margin_bonus += max(0.0, avg_margin) * 2.0
    reign_bonus = 1.0 + 0.15 * coronations + 0.05 * reign_slots
    reliability = judge_reliability if judge_reliability is not None else 0.75
    # BT is primary; win_pct is a mild tie-breaker (avoids double-counting duel outcomes).
    win_factor = 0.8 + 0.2 * (win_pct / 100.0)
    return max(
        1e-6,
        bt_strength * win_factor * margin_bonus * reign_bonus * reliability,
    )


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


def _method_candidates(
    *,
    donor_count: int,
    dominant: float,
    narrow: bool,
    noisy: bool,
) -> list[tuple[str, float, str]]:
    candidates: list[tuple[str, float, str]] = []
    if donor_count == 1 or dominant >= _DOMINANT_DONOR_WEIGHT:
        candidates.append(
            (
                "nuslerp",
                0.9 if donor_count == 1 else 0.85,
                "Single strong donor or one dominant weight — interpolate king ↔ donor with NuSLERP.",
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
                "Noisy judge splits or many donors — DARE + TIES reduces negative synergy.",
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
    return candidates


def _params_for_method(
    method: str,
    *,
    dominant: float,
    narrow: bool,
    noisy: bool,
) -> dict[str, float | bool | str]:
    params: dict[str, float | bool | str] = {}
    if method == "nuslerp":
        t = min(0.65, max(0.12, dominant))
        params["donor_weight"] = round(t, 3)
        params["king_weight"] = round(1.0 - t, 3)
    elif method in ("ties", "dare_ties"):
        params["lambda"] = 1.0
        params["normalize"] = True
        params["default_density"] = round(0.65 if not noisy else 0.45, 2)
        if method == "dare_ties":
            params["rescale"] = True
    elif method == "task_arithmetic":
        params["lambda"] = 0.35 if narrow else 0.6
        params["normalize"] = True
    elif method == "karcher":
        params["max_iter"] = 10
        params["tol"] = 1e-5
    return params


def _build_method_yamls(
    *,
    candidates: list[tuple[str, float, str]],
    base_ref: str,
    donors: list[AlbedoMergeDonorCandidate],
    layer_hints: list[AlbedoMergeLayerHint],
    dominant: float,
    narrow: bool,
    noisy: bool,
    export_all_methods: bool,
) -> list[AlbedoMergeMethodYaml]:
    if not candidates:
        yaml_text = _build_mergekit_yaml(
            method="passthrough",
            base_ref=base_ref,
            donors=donors,
            parameters={},
            layer_hints=layer_hints,
        )
        return [
            AlbedoMergeMethodYaml(
                method="passthrough",
                pretty_name=_METHOD_PRETTY["passthrough"],
                score=1.0,
                is_primary=True,
                yaml=yaml_text,
            )
        ]

    rows: list[AlbedoMergeMethodYaml] = []
    for idx, (method, score, _rationale) in enumerate(candidates[:4 if export_all_methods else 1]):
        params = _params_for_method(method, dominant=dominant, narrow=narrow, noisy=noisy)
        yaml_text = _build_mergekit_yaml(
            method=method,
            base_ref=base_ref,
            donors=donors,
            parameters=params,
            layer_hints=layer_hints,
        )
        rows.append(
            AlbedoMergeMethodYaml(
                method=method,
                pretty_name=_METHOD_PRETTY.get(method, method),
                score=round(score, 3),
                is_primary=idx == 0,
                yaml=yaml_text,
            )
        )
    return rows


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

    candidates = _method_candidates(
        donor_count=donor_count,
        dominant=dominant,
        narrow=narrow,
        noisy=noisy,
    )
    if not candidates:
        return AlbedoMergeMethodRecommendation(
            method="passthrough",
            pretty_name=_METHOD_PRETTY["passthrough"],
            parameters={},
            rationale=["No strong donor models found in the donor pool."],
            alternatives=alternatives,
        )

    method, _score, rationale_line = candidates[0]
    alternatives = [
        AlbedoMergeMethodOption(method=m, score=round(s, 3), rationale=r) for m, s, r in candidates[1:4]
    ]

    params = _params_for_method(method, dominant=dominant, narrow=narrow, noisy=noisy)
    rationale = [rationale_line]
    if method == "nuslerp":
        rationale.append(
            f"NuSLERP weights king={params['king_weight']}, donor={params['donor_weight']}: "
            "interpolate directly between king and top donor (no separate base_model)."
        )
    elif method in ("ties", "dare_ties"):
        rationale.append(
            f"Per-donor density≈{params['default_density']}: retain top-magnitude task-vector weights."
        )
        if method == "dare_ties":
            rationale.append("DARE rescale enabled to recover pruned mass after random sparsification.")
    elif method == "task_arithmetic":
        rationale.append(f"Task arithmetic λ={params['lambda']} keeps the blend conservative on narrow margins.")

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

    doc: dict[str, Any] = {"merge_method": method, "dtype": "bfloat16"}

    if method == "nuslerp":
        top = donors[0] if donors else None
        if not top:
            doc["models"] = [{"model": base_ref}]
            return _yaml_dump(doc)
        donor_w = float(parameters.get("donor_weight", 0.35))
        king_w = float(parameters.get("king_weight", 1.0 - donor_w))
        doc["models"] = [
            {"model": base_ref, "parameters": {"weight": round(king_w, 4)}},
            {"model": top.mergekit_ref, "parameters": {"weight": round(donor_w, 4)}},
        ]
    elif method == "karcher":
        models: list[dict[str, Any]] = [{"model": base_ref}]
        models.extend({"model": donor.mergekit_ref} for donor in donors)
        doc["models"] = models
    else:
        doc["base_model"] = base_ref
        global_params = {
            k: v for k, v in parameters.items() if k not in ("default_density", "donor_weight", "king_weight")
        }
        if global_params:
            doc["parameters"] = global_params
        default_density = parameters.get("default_density")
        doc["models"] = []
        for donor in donors:
            entry: dict[str, Any] = {
                "model": donor.mergekit_ref,
                "parameters": {"weight": round(donor.merge_weight, 4)},
            }
            if default_density is not None:
                density = donor.density if donor.density is not None else float(default_density)
                entry["parameters"]["density"] = round(density, 3)
            doc["models"].append(entry)

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
    mode: MergeAdvisorMode = "current_king",
    king_versions: list[int] | None = None,
    include_past_kings: bool = False,
    min_duels: int = _DEFAULT_MIN_DONOR_DUELS,
    max_donors: int = _MAX_DONORS,
    consensus_only: bool = False,
    export_all_methods: bool = True,
) -> AlbedoMergeAdvisorRecommendation:
    reign_members = (dashboard.get("reign") or {}).get("members") or []
    base_uri = ""
    base_repo = None
    if reign_members:
        base_uri = str(reign_members[0].get("model_uri") or "")
        ns, name, _ = parse_model_uri(base_uri)
        base_repo = f"{ns}/{name}" if ns else name
    base_family = _model_family(base_uri, base_repo)

    eval_runs = _recent_eval_runs(list(dashboard.get("eval_runs") or []))
    coronations = _coronations_from_eval_runs(eval_runs)
    scanned_king_versions = (
        sorted(set(king_versions)) if king_versions else sorted(_king_reign_windows(coronations).keys())
    )

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
    bt_leaderboard = _global_bt_leaderboard(bt, base_uri=base_uri)
    bt_rank_by_uri = {row.model_uri: row.rank for row in bt_leaderboard}

    donor_raw = _collect_donor_stats(
        eval_runs,
        base_uri=base_uri,
        mode=mode,
        king_versions=king_versions,
        include_past_kings=include_past_kings,
        coronation_by_uri=dict(coronation_by_uri),
        reign_slots_by_uri=dict(reign_slots_by_uri),
        coronations=coronations,
    )

    scored: list[tuple[str, float, dict[str, Any]]] = []
    for uri, s in donor_raw.items():
        if not _donor_eligible(
            s,
            min_duels=min_duels,
            include_past_kings=include_past_kings,
            mode=mode,
        ):
            continue
        duels = int(s["duels"])
        win_pct = (s["wins"] / duels * 100.0) if duels else 0.0
        avg_margin = mean(s["margins"]) if s["margins"] else None
        judge_rel = mean(s["reliability"]) if s["reliability"] else None
        bt_strength = bt.get(uri, 1.0)
        raw = _raw_donor_score(
            bt_strength=bt_strength,
            win_pct=win_pct,
            avg_margin=avg_margin,
            coronations=int(s.get("coronations") or 0),
            reign_slots=int(s.get("reign_slots") or 0),
            judge_reliability=judge_rel,
        )
        scored.append(
            (
                uri,
                raw,
                {
                    **s,
                    "win_pct": win_pct,
                    "avg_margin": avg_margin,
                    "judge_rel": judge_rel,
                    "bt": bt_strength,
                },
            )
        )

    scored.sort(key=lambda row: -row[1])
    top = scored[:max_donors]
    weight_scores = {uri: raw for uri, raw, _ in top}
    norm_weights = _normalize_weights(weight_scores)

    donors: list[AlbedoMergeDonorCandidate] = []
    for uri, _raw, meta in top:
        duels = int(meta["duels"])
        wins = int(meta["wins"])
        avg_m = meta.get("avg_margin")
        repo = meta.get("repo")
        density = None
        if avg_m is not None:
            density = round(min(0.8, max(0.25, 0.4 + abs(float(avg_m)))), 3)
        donors.append(
            AlbedoMergeDonorCandidate(
                model_uri=uri,
                repo=repo,
                label=_model_label(uri, repo),
                mergekit_ref=mergekit_model_ref(uri),
                model_family=_model_family(uri, repo),
                sources=sorted(meta.get("sources") or []),
                duels=duels,
                wins=wins,
                losses=duels - wins,
                historical_duels=int(meta.get("historical_duels") or 0),
                win_pct=round(float(meta["win_pct"]), 1),
                avg_margin=round(float(avg_m), 4) if avg_m is not None else None,
                bt_strength=round(float(meta["bt"]), 4),
                global_bt_rank=bt_rank_by_uri.get(uri),
                coronations=int(meta.get("coronations") or 0),
                reign_slots=int(meta.get("reign_slots") or 0),
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
    dominant = max(norm_weights.values()) if norm_weights else 0.0
    narrow = avg_margin is not None and abs(avg_margin) < _NARROW_MARGIN
    noisy = margin_noise > 0.12 or consensus_ratio < 0.5

    method = _select_merge_method(
        donor_count=len(donors),
        weights=norm_weights,
        margin_noise=margin_noise,
        avg_margin=avg_margin,
        consensus_ratio=consensus_ratio,
    )
    layer_hints = _layer_density_hints(len(donors), avg_margin)
    method_candidates = _method_candidates(
        donor_count=len(donors),
        dominant=dominant,
        narrow=narrow,
        noisy=noisy,
    )
    method_yamls = _build_method_yamls(
        candidates=method_candidates,
        base_ref=mergekit_model_ref(base_uri),
        donors=donors,
        layer_hints=layer_hints,
        dominant=dominant,
        narrow=narrow,
        noisy=noisy,
        export_all_methods=export_all_methods,
    )
    yaml_text = method_yamls[0].yaml if method_yamls else _build_mergekit_yaml(
        method="passthrough",
        base_ref=mergekit_model_ref(base_uri),
        donors=donors,
        parameters={},
        layer_hints=layer_hints,
    )

    arch_warnings = _architecture_warnings(base_family, donors)

    data_sources = ["dashboard.json eval_runs", "reign chain (base model)"]
    if mode == "multi_king":
        data_sources.append("multi-king donor pool (reign windows + global BT)")
        if scanned_king_versions:
            data_sources.append(f"king versions scanned: {', '.join(map(str, scanned_king_versions))}")
    if include_past_kings:
        data_sources.append("past coronated kings as donor candidates")
    if consensus_only:
        data_sources.append("judge-consensus duel filter")

    rationale = [
        f"Base model: current king {_model_label(base_uri, base_repo)} ({base_family or 'unknown family'}).",
        f"Mode: {mode.replace('_', ' ')}; min duels={min_duels}; analyzed {duels_analyzed} duels ({consensus_duels} high-consensus).",
    ]
    if donors:
        top_donor = donors[0]
        src = ", ".join(top_donor.sources) if top_donor.sources else "duels"
        rationale.append(
            f"Top donor {top_donor.label}: {top_donor.win_pct:.1f}% win rate over {top_donor.duels} duels "
            f"({top_donor.historical_duels} historical), sources={src}, BT rank "
            f"{top_donor.global_bt_rank or '—'}, merge weight {top_donor.merge_weight:.2f}."
        )
    if arch_warnings:
        rationale.append(arch_warnings[0])
    rationale.extend(method.rationale)

    binary_duels = len(_binary_eval_runs(eval_runs))

    return AlbedoMergeAdvisorRecommendation(
        subnet=subnet,
        generated_at=datetime.now(timezone.utc).isoformat(),
        mode=mode,
        king_versions_scanned=scanned_king_versions,
        include_past_kings=include_past_kings,
        min_duels=min_duels,
        base_model_uri=base_uri,
        base_repo=base_repo,
        base_mergekit_ref=mergekit_model_ref(base_uri),
        base_label=_model_label(base_uri, base_repo),
        base_model_family=base_family,
        donors=donors,
        method=method,
        layer_hints=layer_hints,
        mergekit_yaml=yaml_text,
        method_yamls=method_yamls,
        global_bt_leaderboard=bt_leaderboard,
        architecture_warnings=arch_warnings,
        rationale=rationale,
        data_sources=data_sources,
        duels_analyzed=duels_analyzed,
        binary_duels_analyzed=binary_duels,
        judge_consensus_duels=consensus_duels,
        note=(
            "Recommendations are advisory. Donors must share architecture with the king. "
            "Validate merged checkpoints in real Albedo duels."
        ),
    )


async def get_merge_advisor_recommendation(
    *,
    subnet: int = 97,
    settings: Settings | None = None,
    fresh: bool = False,
    mode: MergeAdvisorMode = "multi_king",
    king_versions: list[int] | None = None,
    include_past_kings: bool = True,
    min_duels: int = _DEFAULT_MIN_DONOR_DUELS,
    max_donors: int = _MAX_DONORS,
    consensus_only: bool = False,
    export_all_methods: bool = True,
) -> AlbedoMergeAdvisorRecommendation:
    settings = settings or get_settings()
    dashboard = await fetch_dashboard(settings=settings)
    return build_merge_advisor_recommendation(
        dashboard,
        subnet=subnet,
        mode=mode,
        king_versions=king_versions,
        include_past_kings=include_past_kings,
        min_duels=min_duels,
        max_donors=max_donors,
        consensus_only=consensus_only,
        export_all_methods=export_all_methods,
    )
