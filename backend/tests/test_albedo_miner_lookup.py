"""Tests for historical miner identity lookup (crown history survives deregistration)."""

from types import SimpleNamespace

from app.services.albedo_miner_lookup import (
    MinerIdentity,
    build_historical_miner_lookup,
    build_miner_lookup,
)
from app.services.albedo_analysis_service import build_analysis_overview


def test_build_historical_miner_lookup_keeps_deregistered_coldkey():
    lookup = build_historical_miner_lookup(
        commitments=[],
        history=[
            SimpleNamespace(
                hotkey="hk_old",
                coldkey="ck_past",
                uid=5,
                repo="org/retired-model",
                model_uri="org/retired-model@sha256:dead",
                commit_block=8_500_000,
            )
        ],
        hotkey_records=[
            SimpleNamespace(hotkey="hk_old", coldkey="ck_past", uid=5),
        ],
        miners=[
            SimpleNamespace(hotkey="hk_old", coldkey="ck_past", uid=5),
        ],
    )

    ident = lookup.resolve(hotkey="hk_old", model_uri="org/retired-model@sha256:dead")
    assert ident is not None
    assert ident.coldkey == "ck_past"
    assert ident.repo == "org/retired-model"

    by_model = lookup.resolve(model_uri="org/retired-model@sha256:other")
    assert by_model is not None
    assert by_model.coldkey == "ck_past"


def test_current_commitment_overrides_stale_history():
    lookup = build_historical_miner_lookup(
        commitments=[
            SimpleNamespace(
                hotkey="hk_a",
                coldkey="ck_new",
                uid=1,
                repo="org/model-a",
                model_uri="org/model-a@sha256:new",
                commit_block=8_520_000,
            )
        ],
        history=[
            SimpleNamespace(
                hotkey="hk_a",
                coldkey="ck_old",
                uid=1,
                repo="org/model-a",
                model_uri="org/model-a@sha256:old",
                commit_block=8_510_000,
            )
        ],
    )

    ident = lookup.resolve(hotkey="hk_a")
    assert ident is not None
    assert ident.coldkey == "ck_new"
    assert ident.commit_block == 8_520_000


def test_king_history_retains_coldkey_without_active_commitment():
    lookup = build_historical_miner_lookup(
        commitments=[],
        history=[
            SimpleNamespace(
                hotkey="hk_a",
                coldkey="ck_owner1",
                uid=1,
                repo="org/model-a",
                model_uri="org/model-a@sha256:1",
                commit_block=8_500_000,
            ),
        ],
        miners=[SimpleNamespace(hotkey="hk_a", coldkey="ck_owner1", uid=1)],
    )

    dashboard = {
        "updated_at": "2026-06-27T14:00:00+00:00",
        "chain": {"judge_models": []},
        "reign": {"members": []},
        "current_eval": None,
        "queue": [],
        "eval_runs": [
            {
                "eval_run_id": "c1",
                "challenger_won": True,
                "coronated": True,
                "king_version": 1,
                "score_challenger": 0.6,
                "score_king": 0.4,
                "win_margin": 0.2,
                "finished_at": "2026-06-26T10:00:00+00:00",
                "model_uri": "org/model-a@sha256:1",
                "hotkey": "hk_a",
                "uid": 1,
                "score_breakdown": {"by_judge": {}, "by_metric": {}},
                "king": {"king_version": 0, "model_uri": "org/other@sha256:0", "uid": 99, "hotkey": "hk_old"},
            },
        ],
    }

    overview = build_analysis_overview(
        dashboard,
        subnet=97,
        source_url="https://example.com/dashboard.json",
        miner_lookup=lookup,
    )

    assert overview.king_history[0].coldkey == "ck_owner1"


def test_build_miner_lookup_still_works_for_active_only():
    lookup = build_miner_lookup(
        [
            SimpleNamespace(
                hotkey="hk1",
                coldkey="ck1",
                uid=2,
                repo="org/x",
                model_uri="org/x@sha256:a",
                commit_block=1,
            )
        ]
    )
    assert lookup.resolve(hotkey="hk1") == MinerIdentity(coldkey="ck1", repo="org/x", uid=2, commit_block=1)
