"""Tests for per-sample score gap analysis."""

import asyncio

from app.services.albedo_sample_score_analysis_service import (
    analyze_sample_rows,
    build_sample_score_analysis,
    classify_sample_gap,
    rubric_score_pct,
)


def _uniform_row(
    *,
    sample_id: str,
    question_count: int,
    ch_ones: int,
    k_ones: int,
    judges: list[str] | None = None,
) -> dict:
    judges = judges or ["z-ai/glm-5.1", "qwen/qwen3.5-397b-a17b", "deepseek/deepseek-v3.2"]
    questions = [{"id": f"q_{i:02d}", "text": f"Q{i}"} for i in range(1, question_count + 1)]
    ch_answers = {q["id"]: "1" if i <= ch_ones else "0" for i, q in enumerate(questions, start=1)}
    k_answers = {q["id"]: "1" if i <= k_ones else "0" for i, q in enumerate(questions, start=1)}
    judge_results = []
    for judge in judges:
        judge_results.extend(
            [
                {"judge_model": judge, "side": "challenger", "answers": ch_answers, "explanations": {}},
                {"judge_model": judge, "side": "previous_king", "answers": k_answers, "explanations": {}},
            ]
        )
    return {"sample_id": sample_id, "questions": questions, "judge_results": judge_results}


def test_classify_sample_gap_buckets():
    assert classify_sample_gap(100.0, 0.0) == "decisive"
    assert classify_sample_gap(80.0, 50.0) == "moderate"
    assert classify_sample_gap(60.0, 50.0) == "close"
    assert classify_sample_gap(70.0, 10.0) == "moderate"  # wide gap but leader <= 90


def test_rubric_score_pct():
    answers = {"q_01": "1", "q_02": "0", "q_03": "1"}
    assert abs(rubric_score_pct(answers, ["q_01", "q_02", "q_03"]) - 200 / 3) < 0.01


def test_analyze_sample_rows_emits_per_judge_observations():
    rows = [
        _uniform_row(sample_id="s1", question_count=10, ch_ones=10, k_ones=0),
        _uniform_row(sample_id="s2", question_count=10, ch_ones=8, k_ones=5),
    ]
    obs = analyze_sample_rows(
        rows,
        eval_run_id="duel-a",
        finished_at="2026-06-27T10:00:00+00:00",
        challenger_label="uid 1",
        king_label="uid 2",
        winner="challenger",
    )
    assert len(obs) == 6  # 2 samples × 3 judges
    assert sum(1 for o in obs if o.bucket == "decisive") == 3
    assert sum(1 for o in obs if o.bucket == "moderate") == 3
    assert obs[0].margin == 1.0
    assert obs[0].margin_abs == 1.0


def test_gap_type_margin_share_and_distribution():
    rows = [_uniform_row(sample_id="s1", question_count=10, ch_ones=10, k_ones=0)]
    obs = analyze_sample_rows(rows, eval_run_id="duel-a")
    result = build_sample_score_analysis(obs)

    assert len(result.gap_types) == 3
    decisive = next(t for t in result.gap_types if t.gap_type == "decisive")
    assert decisive.share_pct == 100.0
    assert decisive.avg_margin_pct == 100.0
    assert len(decisive.gap_distribution) == 5
    top_bin = max(decisive.gap_distribution, key=lambda b: b.share_pct)
    assert top_bin.share_pct == 100.0

    assert len(result.judge_margin_shares) == 3
    assert result.judge_margin_shares[0].share_pct == 33.33
    assert len(result.judge_margin_shares[0].by_gap_type) == 3
    assert result.duels[0].gap_types[2].share_pct == 100.0


def test_build_sample_score_analysis_aggregates_duels_and_judges():
    rows_a = [_uniform_row(sample_id="s1", question_count=10, ch_ones=10, k_ones=0)]
    rows_b = [_uniform_row(sample_id="s2", question_count=10, ch_ones=6, k_ones=5)]
    obs = analyze_sample_rows(rows_a, eval_run_id="duel-a", finished_at="2026-06-28T10:00:00+00:00")
    obs.extend(analyze_sample_rows(rows_b, eval_run_id="duel-b", finished_at="2026-06-27T10:00:00+00:00"))
    result = build_sample_score_analysis(obs)

    assert result.total_observations == 6
    assert result.binary_duels_with_samples == 2
    assert len(result.by_judge) == 3
    decisive_share = next(t.share_pct for t in result.gap_types if t.gap_type == "decisive")
    close_share = next(t.share_pct for t in result.gap_types if t.gap_type == "close")
    assert decisive_share == 90.91
    assert close_share == 9.09
    assert len(result.judge_pairs) == 3
    assert result.duels[0].eval_run_id == "duel-a"


def test_get_sample_score_analysis_scans_binary_duels(monkeypatch):
    rows = [_uniform_row(sample_id="s1", question_count=10, ch_ones=10, k_ones=0)]

    async def fake_fetch_dashboard(*, settings=None, fresh=False):
        return {
            "updated_at": "2026-06-27T12:00:00+00:00",
            "eval_runs": [
                {
                    "eval_run_id": "duel-a",
                    "scoring_mode": "binary",
                    "uid": 10,
                    "challenger_won": True,
                    "finished_at": "2026-06-27T10:00:00+00:00",
                    "king": {"uid": 5},
                    "artifacts": {"SCORING_RESULTS": "https://example.com/a.jsonl"},
                },
                {
                    "eval_run_id": "legacy",
                    "scoring_mode": "glm_categories",
                    "artifacts": {"SCORING_RESULTS": "https://example.com/legacy.jsonl"},
                },
            ],
        }

    async def fake_fetch_scoring_results_jsonl(url, *, settings=None, client=None, fresh=False):
        return rows

    from app.services import albedo_sample_score_analysis_service as svc

    monkeypatch.setattr(svc, "fetch_dashboard", fake_fetch_dashboard)
    monkeypatch.setattr(svc, "fetch_scoring_results_jsonl", fake_fetch_scoring_results_jsonl)

    result = asyncio.run(svc.get_sample_score_analysis(fresh=True))
    assert result.binary_duels_total == 1
    assert result.binary_duels_scanned == 1
    assert result.total_observations == 3
    assert result.duels[0].challenger_label == "uid 10"
