"""Tests for Albedo scoring-results dual-zero / dual-one analysis."""

import asyncio
import json

from app.integrations.albedo_scoring_results import parse_scoring_results_jsonl
from app.services.albedo_scoring_analysis_service import (
    analyze_dual_one_questions,
    analyze_dual_zero_questions,
    build_binary_consensus_dataset_for_kings,
    build_binary_dual_one_dataset,
    build_binary_dual_zero_dataset,
    build_consensus_export,
    build_dual_zero_export_jsonl,
    build_sample_export_json,
    dedupe_records_by_sample_id,
    duel_export_filename,
    sample_meets_export_question_minimum,
)


def _sample_row(
    *,
    sample_id: str,
    glm_q1: str = "0",
    qwen_q1: str = "0",
    glm_q2: str = "1",
    qwen_q2: str = "0",
    king_glm_q1: str = "0",
    king_qwen_q1: str = "0",
) -> dict:
    return {
        "sample_id": sample_id,
        "questions": [
            {"id": "q_01", "category": "overall", "text": "Runs test suite?", "example_bad": "Only runs git diff."},
            {"id": "q_02", "category": "pytest", "text": "Uses pytest -x?"},
        ],
        "judge_results": [
            {
                "judge_model": "z-ai/glm-5.1",
                "side": "challenger",
                "answers": {"q_01": glm_q1, "q_02": glm_q2},
                "explanations": {
                    "q_01": "ch GLM: no test suite.",
                    "q_02": "ch GLM: pytest -x present.",
                },
            },
            {
                "judge_model": "qwen/qwen3.5-397b-a17b",
                "side": "challenger",
                "answers": {"q_01": qwen_q1, "q_02": qwen_q2},
                "explanations": {
                    "q_01": "ch Qwen: only git diff.",
                    "q_02": "ch Qwen: no -x flag.",
                },
            },
            {
                "judge_model": "z-ai/glm-5.1",
                "side": "previous_king",
                "answers": {"q_01": king_glm_q1, "q_02": "1"},
                "explanations": {
                    "q_01": "k GLM: no test suite.",
                    "q_02": "k GLM: ok",
                },
            },
            {
                "judge_model": "qwen/qwen3.5-397b-a17b",
                "side": "previous_king",
                "answers": {"q_01": king_qwen_q1, "q_02": "1"},
                "explanations": {
                    "q_01": "k Qwen: no test suite.",
                    "q_02": "k Qwen: ok",
                },
            },
        ],
    }


def _sample_row_with_questions(
    *,
    sample_id: str,
    question_count: int,
    polarity: str = "zero",
) -> dict:
    score = "0" if polarity == "zero" else "1"
    questions = [
        {"id": f"q_{i:02d}", "category": "overall", "text": f"Question {i}?"}
        for i in range(1, question_count + 1)
    ]
    answers = {f"q_{i:02d}": score for i in range(1, question_count + 1)}
    explanations = {qid: f"{qid} reason" for qid in answers}
    judge_results = [
        {"judge_model": "z-ai/glm-5.1", "side": "challenger", "answers": answers, "explanations": explanations},
        {"judge_model": "qwen/qwen3.5-397b-a17b", "side": "challenger", "answers": answers, "explanations": explanations},
        {"judge_model": "z-ai/glm-5.1", "side": "previous_king", "answers": answers, "explanations": explanations},
        {"judge_model": "qwen/qwen3.5-397b-a17b", "side": "previous_king", "answers": answers, "explanations": explanations},
    ]
    return {"sample_id": sample_id, "questions": questions, "judge_results": judge_results}


def test_parse_scoring_results_jsonl():
    payload = "\n".join(
        [
            json.dumps({"sample_id": "a", "questions": [], "judge_results": []}),
            "",
            json.dumps({"sample_id": "b", "questions": [], "judge_results": []}),
        ]
    )
    rows = parse_scoring_results_jsonl(payload)
    assert len(rows) == 2
    assert rows[0]["sample_id"] == "a"


def test_analyze_dual_zero_requires_both_sides():
    rows = [
        _sample_row(sample_id="dataset/a:1:1"),
        _sample_row(sample_id="dataset/b:2:2", glm_q1="1", qwen_q1="0"),
    ]
    analysis = analyze_dual_zero_questions(rows)

    assert analysis.total_samples == 2
    assert analysis.samples_with_dual_zeros == 1
    assert analysis.samples[0].sample_id == "dataset/a:1:1"


def test_duel_export_filename():
    assert (
        duel_export_filename(king_uid=50, challenger_uid=205, winner="king")
        == "50 vs 205 king dual-zero.jsonl"
    )
    assert (
        duel_export_filename(king_uid=50, challenger_uid=205, winner="challenger", polarity="one")
        == "50 vs 205 challenger dual-one.jsonl"
    )


def test_analyze_dual_one_requires_both_sides():
    rows = [
        _sample_row(
            sample_id="dataset/a:1:1",
            glm_q1="1",
            qwen_q1="1",
            king_glm_q1="1",
            king_qwen_q1="1",
        ),
        _sample_row(sample_id="dataset/b:2:2", glm_q1="1", qwen_q1="0"),
    ]
    analysis = analyze_dual_one_questions(rows)

    assert analysis.polarity == "one"
    assert analysis.total_samples == 2
    assert analysis.samples_with_dual_zeros == 1
    assert analysis.samples[0].sample_id == "dataset/a:1:1"
    assert analysis.samples[0].questions[0].question_id == "q_01"


def test_build_dual_zero_export_jsonl_is_multiline_jsonl():
    rows = [
        _sample_row_with_questions(sample_id="dataset/a:1:1", question_count=6),
        _sample_row_with_questions(sample_id="dataset/e:5:5", question_count=6),
    ]
    analysis = analyze_dual_zero_questions(rows)
    payload = build_dual_zero_export_jsonl(analysis)
    lines = [line for line in payload.splitlines() if line.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["sample_id"] == "dataset/a:1:1"


def test_build_dual_zero_export_skips_samples_with_five_or_fewer_questions():
    rows = [
        _sample_row_with_questions(sample_id="dataset/short:1:1", question_count=5),
        _sample_row_with_questions(sample_id="dataset/long:2:2", question_count=6),
    ]
    analysis = analyze_dual_zero_questions(rows)
    by_id = {sample.sample_id: sample for sample in analysis.samples}
    assert sample_meets_export_question_minimum(by_id["dataset/short:1:1"]) is False
    assert sample_meets_export_question_minimum(by_id["dataset/long:2:2"]) is True
    payload = build_dual_zero_export_jsonl(analysis)
    lines = [line for line in payload.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["sample_id"] == "dataset/long:2:2"
    assert len(json.loads(lines[0])["questions"]) == 6


def test_build_dual_zero_export_single_jsonl_file():
    rows = [_sample_row_with_questions(sample_id="dataset/a:1:1", question_count=6)]
    analysis = analyze_dual_zero_questions(rows)
    payload = build_consensus_export(
        analysis,
        king_uid=50,
        challenger_uid=205,
        winner="king",
    )

    assert payload.media_type == "application/x-ndjson"
    assert payload.filename == "50 vs 205 king dual-zero.jsonl"
    lines = payload.content.decode().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert set(record.keys()) == {"sample_id", "questions"}
    assert set(record["questions"][0].keys()) == {
        "question_id",
        "text",
        "example_bad",
        "challenger_glm",
        "challenger_qwen",
        "king_glm",
        "king_qwen",
    }
    assert record["questions"][0]["text"] == "Question 1?"
    assert record["questions"][0]["example_bad"] is None


def test_build_sample_export_json_minimal_shape():
    rows = [_sample_row(sample_id="dataset/a:1:1")]
    analysis = analyze_dual_zero_questions(rows)
    record = json.loads(build_sample_export_json(analysis.samples[0]).strip())
    assert "eval_run_id" not in record
    assert record["sample_id"] == "dataset/a:1:1"


def test_dedupe_records_by_sample_id_keeps_first():
    records = [
        {"sample_id": "dataset/a:1:1", "questions": [{"question_id": "q_01"}]},
        {"sample_id": "dataset/b:2:2", "questions": []},
        {"sample_id": "dataset/a:1:1", "questions": [{"question_id": "q_02"}]},
    ]
    unique, removed = dedupe_records_by_sample_id(records)
    assert removed == 1
    assert len(unique) == 2
    assert unique[0]["questions"][0]["question_id"] == "q_01"


def test_build_binary_dual_zero_dataset_dedupes_across_duels(monkeypatch):
    rows_a = [_sample_row_with_questions(sample_id="dataset/a:1:1", question_count=6)]
    rows_b = [
        _sample_row_with_questions(sample_id="dataset/a:1:1", question_count=6),
        _sample_row_with_questions(sample_id="dataset/c:3:3", question_count=6),
    ]

    async def fake_fetch_dashboard(*, settings=None, fresh=False):
        return {
            "eval_runs": [
                {
                    "eval_run_id": "duel-a",
                    "scoring_mode": "binary",
                    "artifacts": {"SCORING_RESULTS": "https://example.com/a.jsonl"},
                },
                {
                    "eval_run_id": "duel-b",
                    "scoring_mode": "binary",
                    "artifacts": {"SCORING_RESULTS": "https://example.com/b.jsonl"},
                },
                {
                    "eval_run_id": "legacy",
                    "scoring_mode": "glm_categories",
                    "artifacts": {"SCORING_RESULTS": "https://example.com/legacy.jsonl"},
                },
            ]
        }

    async def fake_fetch_scoring_results_jsonl(url, *, settings=None, client=None, fresh=False):
        if url.endswith("/a.jsonl"):
            return rows_a
        if url.endswith("/b.jsonl"):
            return rows_b
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        "app.services.albedo_scoring_analysis_service.fetch_dashboard",
        fake_fetch_dashboard,
    )
    monkeypatch.setattr(
        "app.services.albedo_scoring_analysis_service.fetch_scoring_results_jsonl",
        fake_fetch_scoring_results_jsonl,
    )

    result = asyncio.run(build_binary_dual_zero_dataset(fresh=True))
    assert result.summary.binary_duels_total == 2
    assert result.summary.binary_duels_with_scoring == 2
    assert result.summary.binary_duels_scanned == 2
    assert result.summary.recent_duels_limit == 20
    assert result.summary.binary_duels_with_dual_zero == 2
    assert result.summary.samples_before_dedup == 3
    assert result.summary.unique_samples == 2
    assert result.summary.duplicates_removed == 1
    assert {record["sample_id"] for record in result.records} == {"dataset/a:1:1", "dataset/c:3:3"}


def test_build_binary_dual_one_dataset_uses_one_polarity(monkeypatch):
    rows = [_sample_row_with_questions(sample_id="dataset/a:1:1", question_count=6, polarity="one")]

    async def fake_fetch_dashboard(*, settings=None, fresh=False):
        return {
            "eval_runs": [
                {
                    "eval_run_id": "duel-a",
                    "scoring_mode": "binary",
                    "artifacts": {"SCORING_RESULTS": "https://example.com/a.jsonl"},
                },
            ]
        }

    async def fake_fetch_scoring_results_jsonl(url, *, settings=None, client=None, fresh=False):
        return rows

    monkeypatch.setattr(
        "app.services.albedo_scoring_analysis_service.fetch_dashboard",
        fake_fetch_dashboard,
    )
    monkeypatch.setattr(
        "app.services.albedo_scoring_analysis_service.fetch_scoring_results_jsonl",
        fake_fetch_scoring_results_jsonl,
    )

    result = asyncio.run(build_binary_dual_one_dataset(fresh=True))
    assert result.summary.polarity == "one"
    assert result.summary.export_filename == "binary-dual-one-dataset.jsonl"
    assert result.summary.unique_samples == 1
    assert result.records[0]["questions"][0]["question_id"] == "q_01"


def test_build_binary_dataset_scans_only_latest_twenty_duels(monkeypatch):
    rows = [_sample_row_with_questions(sample_id="dataset/a:1:1", question_count=6)]
    fetched_urls: list[str] = []

    async def fake_fetch_dashboard(*, settings=None, fresh=False):
        runs = []
        for i in range(25):
            runs.append(
                {
                    "eval_run_id": f"duel-{i:02d}",
                    "scoring_mode": "binary",
                    "finished_at": f"2026-06-{(i % 28) + 1:02d}T10:00:00+00:00",
                    "artifacts": {"SCORING_RESULTS": f"https://example.com/{i:02d}.jsonl"},
                }
            )
        return {"eval_runs": runs}

    async def fake_fetch_scoring_results_jsonl(url, *, settings=None, client=None, fresh=False):
        fetched_urls.append(url)
        return rows

    monkeypatch.setattr(
        "app.services.albedo_scoring_analysis_service.fetch_dashboard",
        fake_fetch_dashboard,
    )
    monkeypatch.setattr(
        "app.services.albedo_scoring_analysis_service.fetch_scoring_results_jsonl",
        fake_fetch_scoring_results_jsonl,
    )

    result = asyncio.run(build_binary_dual_zero_dataset(fresh=True))
    assert result.summary.binary_duels_with_scoring == 25
    assert result.summary.binary_duels_scanned == 20
    assert len(fetched_urls) == 20
    assert fetched_urls[0].endswith("/24.jsonl")
    assert fetched_urls[-1].endswith("/05.jsonl")


def test_build_king_reign_dataset_filters_duels_by_reign_window(monkeypatch):
    rows_v1 = [_sample_row_with_questions(sample_id="dataset/king1:1:1", question_count=6)]
    rows_v2 = [_sample_row_with_questions(sample_id="dataset/king2:2:2", question_count=6)]
    fetched_urls: list[str] = []

    async def fake_fetch_dashboard(*, settings=None, fresh=False):
        return {
            "eval_runs": [
                {
                    "eval_run_id": "coronation-v1",
                    "coronated": True,
                    "king_version": 1,
                    "finished_at": "2026-06-01T10:00:00+00:00",
                    "model_uri": "org/king-v1@sha256:1",
                    "uid": 1,
                    "hotkey": "hk_v1",
                    "king": {"king_version": 0, "model_uri": "org/genesis@sha256:0", "uid": 0, "hotkey": "hk0"},
                },
                {
                    "eval_run_id": "coronation-v2",
                    "coronated": True,
                    "king_version": 2,
                    "finished_at": "2026-06-10T10:00:00+00:00",
                    "model_uri": "org/king-v2@sha256:2",
                    "uid": 2,
                    "hotkey": "hk_v2",
                    "king": {"king_version": 1, "model_uri": "org/king-v1@sha256:1", "uid": 1, "hotkey": "hk_v1"},
                },
                {
                    "eval_run_id": "duel-v1-early",
                    "scoring_mode": "binary",
                    "finished_at": "2026-05-31T10:00:00+00:00",
                    "king": {"king_version": 1},
                    "artifacts": {"SCORING_RESULTS": "https://example.com/v1-early.jsonl"},
                },
                {
                    "eval_run_id": "duel-v1-mid",
                    "scoring_mode": "binary",
                    "finished_at": "2026-06-05T10:00:00+00:00",
                    "king": {"king_version": 1},
                    "artifacts": {"SCORING_RESULTS": "https://example.com/v1-mid.jsonl"},
                },
                {
                    "eval_run_id": "duel-v2-mid",
                    "scoring_mode": "binary",
                    "finished_at": "2026-06-15T10:00:00+00:00",
                    "king": {"king_version": 2},
                    "artifacts": {"SCORING_RESULTS": "https://example.com/v2-mid.jsonl"},
                },
                {
                    "eval_run_id": "duel-v1-wrong-king",
                    "scoring_mode": "binary",
                    "finished_at": "2026-06-06T10:00:00+00:00",
                    "king": {"king_version": 2},
                    "artifacts": {"SCORING_RESULTS": "https://example.com/wrong.jsonl"},
                },
            ]
        }

    async def fake_fetch_scoring_results_jsonl(url, *, settings=None, client=None, fresh=False):
        fetched_urls.append(url)
        if url.endswith("/v1-mid.jsonl"):
            return rows_v1
        if url.endswith("/v2-mid.jsonl"):
            return rows_v2
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(
        "app.services.albedo_scoring_analysis_service.fetch_dashboard",
        fake_fetch_dashboard,
    )
    monkeypatch.setattr(
        "app.services.albedo_scoring_analysis_service.fetch_scoring_results_jsonl",
        fake_fetch_scoring_results_jsonl,
    )

    result = asyncio.run(build_binary_consensus_dataset_for_kings([1, 2], fresh=True))
    assert result.summary.build_mode == "king_reign"
    assert result.summary.king_versions == [1, 2]
    assert result.summary.binary_duels_scanned == 2
    assert len(fetched_urls) == 2
    assert result.summary.unique_samples == 2
    assert {record["sample_id"] for record in result.records} == {
        "dataset/king1:1:1",
        "dataset/king2:2:2",
    }
    breakdown = {row.king_version: row for row in result.summary.king_reign_breakdown}
    assert breakdown[1].binary_duels_scanned == 1
    assert breakdown[1].binary_duels_with_dual_zero == 1
    assert breakdown[2].binary_duels_scanned == 1
    assert breakdown[2].binary_duels_with_dual_zero == 1
