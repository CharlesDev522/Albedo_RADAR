"""Tests for priority miner discovery."""

from app.processing.priority_miner_discovery import _repos_from_dashboard


def test_repos_from_dashboard_filters_priority_namespaces():
    dashboard = {
        "eval_runs": [
            {
                "model_uri": "cyantest/albedo-qwen3.6-35b-7777@sha256:abc",
                "king": {"model_uri": "booksome/albedo-qwen3.6-35b-testc@sha256:def"},
            },
            {"model_uri": "other/albedo-qwen3.6-35b-x@sha256:zzz"},
        ],
        "reign": {
            "members": [
                {"model_uri": "divinequest/albedo-qwen3.6-35b-g5ap8a74@sha256:111"},
            ]
        },
    }
    repos = _repos_from_dashboard(
        dashboard,
        {"cyantest", "booksome", "divinequest"},
    )
    assert repos == {
        "cyantest/albedo-qwen3.6-35b-7777",
        "booksome/albedo-qwen3.6-35b-testc",
        "divinequest/albedo-qwen3.6-35b-g5ap8a74",
    }
