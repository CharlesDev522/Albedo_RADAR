"""Tests for Albedo scoring-results dual-zero / dual-one analysis."""

import asyncio
import json

from app.integrations.albedo_scoring_results import parse_scoring_results_jsonl
from app.services.albedo_scoring_analysis_service import (
    analyze_dual_one_questions,
    analyze_dual_zero_questions,
    build_binary_dual_one_dataset,
    build_binary_dual_zero_dataset,
    build_consensus_export,
    build_dual_zero_export_jsonl,
    build_sample_export_json,
    dedupe_records_by_sample_id,
    duel_export_filename,
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
        _sample_row(sample_id="dataset/a:1:1"),
        _sample_row(sample_id="dataset/e:5:5"),
    ]
    analysis = analyze_dual_zero_questions(rows)
    payload = build_dual_zero_export_jsonl(analysis)
    lines = [line for line in payload.splitlines() if line.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["sample_id"] == "dataset/a:1:1"


def test_build_dual_zero_export_single_jsonl_file():
    rows = [_sample_row(sample_id="dataset/a:1:1")]
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
    assert record["questions"][0]["text"] == "Runs test suite?"
    assert record["questions"][0]["example_bad"] == "Only runs git diff."


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
    rows_a = [_sample_row(sample_id="dataset/a:1:1")]
    rows_b = [_sample_row(sample_id="dataset/a:1:1"), _sample_row(sample_id="dataset/c:3:3")]

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
    assert result.summary.recent_duels_limit == 16
    assert result.summary.binary_duels_with_dual_zero == 2
    assert result.summary.samples_before_dedup == 3
    assert result.summary.unique_samples == 2
    assert result.summary.duplicates_removed == 1
    assert {record["sample_id"] for record in result.records} == {"dataset/a:1:1", "dataset/c:3:3"}


def test_build_binary_dual_one_dataset_uses_one_polarity(monkeypatch):
    rows = [
        _sample_row(
            sample_id="dataset/a:1:1",
            glm_q1="1",
            qwen_q1="1",
            king_glm_q1="1",
            king_qwen_q1="1",
        )
    ]

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


def test_build_binary_dataset_scans_only_latest_sixteen_duels(monkeypatch):
    rows = [_sample_row(sample_id="dataset/a:1:1")]
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
