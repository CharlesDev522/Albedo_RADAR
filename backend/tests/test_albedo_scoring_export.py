"""Tests for simple scoring-results.jsonl export."""

import asyncio
from unittest.mock import patch

import pytest

from app.integrations.albedo_scoring_results import (
    count_scoring_results_lines,
    parse_scoring_results_jsonl,
    scoring_results_url,
)
from app.services.albedo_scoring_export_service import (
    export_scoring_results_for_eval,
    get_scoring_export_overview,
)


def test_scoring_results_url_reads_artifact_keys():
    assert scoring_results_url({"artifacts": {"SCORING_RESULTS": "https://x/s.jsonl"}}) == "https://x/s.jsonl"
    assert scoring_results_url({"artifacts": {"scoring_results": "https://x/s.jsonl"}}) == "https://x/s.jsonl"
    assert scoring_results_url({"artifacts": {}}) is None


def test_parse_scoring_results_jsonl_skips_blank_lines():
    rows = parse_scoring_results_jsonl('{"sample_id":"a"}\n\n{"sample_id":"b"}\n')
    assert len(rows) == 2
    assert rows[0]["sample_id"] == "a"


def test_count_scoring_results_lines():
    assert count_scoring_results_lines('{"a":1}\n\n{"b":2}\n') == 2


def test_get_scoring_export_overview_lists_duels_with_artifacts():
    dashboard = {
        "eval_runs": [
            {
                "eval_run_id": "run-without",
                "finished_at": "2026-06-27T12:00:00+00:00",
                "model_uri": "org/a@sha256:1",
                "challenger_won": False,
                "coronated": False,
            },
            {
                "eval_run_id": "run-with-scoring",
                "finished_at": "2026-06-27T11:00:00+00:00",
                "model_uri": "org/b@sha256:2",
                "challenger_won": True,
                "coronated": False,
                "scoring_mode": "binary",
                "scored_sample_count": 12,
                "artifacts": {"SCORING_RESULTS": "https://example.com/scoring.jsonl"},
                "king": {"model_uri": "org/king@sha256:9"},
            },
        ]
    }

    async def fake_fetch_dashboard(*_args, **_kwargs):
        return dashboard

    with patch(
        "app.services.albedo_scoring_export_service.fetch_dashboard",
        side_effect=fake_fetch_dashboard,
    ):
        overview = asyncio.run(get_scoring_export_overview())

    assert overview.duels_total == 2
    assert overview.duels_with_scoring == 1
    assert len(overview.duels) == 1
    assert overview.duels[0].eval_run_id == "run-with-scoring"
    assert overview.duels[0].export_filename == "scoring-results-run-with.jsonl"


def test_export_scoring_results_for_eval_downloads_raw_jsonl():
    dashboard = {
        "eval_runs": [
            {
                "eval_run_id": "run-abc12345",
                "artifacts": {"SCORING_RESULTS": "https://example.com/scoring.jsonl"},
            }
        ]
    }
    raw = '{"sample_id":"s1"}\n{"sample_id":"s2"}\n'

    async def fake_fetch_dashboard(*_args, **_kwargs):
        return dashboard

    async def fake_fetch_text(url, **_kwargs):
        assert url == "https://example.com/scoring.jsonl"
        return raw

    with patch(
        "app.services.albedo_scoring_export_service.fetch_dashboard",
        side_effect=fake_fetch_dashboard,
    ), patch(
        "app.services.albedo_scoring_export_service.fetch_scoring_results_text",
        side_effect=fake_fetch_text,
    ):
        payload = asyncio.run(export_scoring_results_for_eval("run-abc12345"))

    assert payload.filename == "scoring-results-run-abc1.jsonl"
    assert payload.content.decode("utf-8") == raw


def test_export_scoring_results_missing_artifact_raises():
    dashboard = {"eval_runs": [{"eval_run_id": "run-missing", "artifacts": {}}]}

    async def fake_fetch_dashboard(*_args, **_kwargs):
        return dashboard

    with patch(
        "app.services.albedo_scoring_export_service.fetch_dashboard",
        side_effect=fake_fetch_dashboard,
    ):
        with pytest.raises(LookupError, match="No scoring-results artifact"):
            asyncio.run(export_scoring_results_for_eval("run-missing"))
