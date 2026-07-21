"""Tests for voided king detection."""

from app.services.albedo_king_history import filter_voided_coronations, voided_king_versions
from app.schemas.albedo_analysis import AlbedoKingCoronation


def test_voided_king_versions_detects_rolled_back_coronations():
    dashboard = {
        "reign": {
            "members": [
                {"king_version": 84},
                {"king_version": 83},
                {"king_version": 81},
                {"king_version": 80},
            ]
        },
        "eval_runs": [
            {"coronated": True, "king_version": 89},
            {"coronated": True, "king_version": 88},
            {"coronated": True, "king_version": 87},
            {"coronated": True, "king_version": 86},
            {"coronated": True, "king_version": 85},
            {"coronated": True, "king_version": 84},
            {"coronated": True, "king_version": 82},
        ],
    }
    assert voided_king_versions(dashboard) == {85, 86, 87, 88, 89}


def test_filter_voided_coronations():
    rows = [
        AlbedoKingCoronation(
            king_version=84,
            model_uri="a/b@sha",
            model_name="b",
            namespace="a",
            hotkey="hk",
            uid=1,
            finished_at="2026-07-15T00:00:00+00:00",
            eval_run_id="r84",
            score_challenger=0.9,
            score_king=0.8,
            win_margin=0.1,
        ),
        AlbedoKingCoronation(
            king_version=89,
            model_uri="c/d@sha",
            model_name="d",
            namespace="c",
            hotkey="hk2",
            uid=2,
            finished_at="2026-07-18T00:00:00+00:00",
            eval_run_id="r89",
            score_challenger=0.9,
            score_king=0.8,
            win_margin=0.1,
        ),
    ]
    filtered = filter_voided_coronations(rows, {89})
    assert [r.king_version for r in filtered] == [84]
