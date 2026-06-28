"""Tests for priority miner discovery."""

from app.processing.priority_miner_discovery import (
    _repos_from_dashboard,
    compute_challenger_stats,
    resolve_watch_namespaces,
)


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


def test_compute_challenger_stats_and_top_namespaces():
    dashboard = {
        "eval_runs": [
            {
                "model_uri": "cyantest/albedo-qwen3.6-35b-a@sha256:1",
                "challenger_won": True,
                "coronated": False,
            },
            {
                "model_uri": "cyantest/albedo-qwen3.6-35b-b@sha256:2",
                "challenger_won": False,
                "coronated": False,
            },
            {
                "model_uri": "sota1028/albedo-qwen3.6-35b-x@sha256:3",
                "challenger_won": True,
                "coronated": True,
            },
            {
                "model_uri": "sota1028/albedo-qwen3.6-35b-y@sha256:4",
                "challenger_won": True,
                "coronated": False,
            },
            {
                "model_uri": "sota1028/albedo-qwen3.6-35b-z@sha256:5",
                "challenger_won": False,
                "coronated": False,
            },
        ]
    }
    ns_stats, repo_stats = compute_challenger_stats(dashboard)
    assert ns_stats["cyantest"].duels == 2
    assert ns_stats["sota1028"].duels == 3
    assert repo_stats["sota1028/albedo-qwen3.6-35b-x"].coronations == 1

    from app.config import Settings

    settings = Settings(
        priority_miner_namespaces=["cyantest"],
        priority_challenger_top_n=2,
    )
    watch = resolve_watch_namespaces(settings, dashboard)
    namespaces = [w.namespace for w in watch]
    assert namespaces[0] == "cyantest"
    assert "sota1028" in namespaces
    top = next(w for w in watch if w.namespace == "sota1028")
    assert top.source == "top_challenger"
    assert top.rank == 1
