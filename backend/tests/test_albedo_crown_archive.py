"""Tests for archived king crown history."""

from app.schemas.albedo_analysis import AlbedoKingCoronation
from app.services.albedo_king_history import merge_king_histories


def test_merge_king_histories_keeps_older_archived_versions():
    archived = [
        AlbedoKingCoronation(
            king_version=12,
            model_uri="org/old@sha256:1",
            model_name="old",
            namespace="org",
            repo="org/old",
            coldkey="ck_old",
            hotkey="hk_old",
            uid=1,
            finished_at="2026-06-20T10:00:00+00:00",
            eval_run_id="arch-12",
            score_challenger=0.6,
            score_king=0.4,
            win_margin=0.2,
        )
    ]
    live = [
        AlbedoKingCoronation(
            king_version=13,
            model_uri="org/new@sha256:2",
            model_name="new",
            namespace="org",
            repo="org/new",
            coldkey="ck_new",
            hotkey="hk_new",
            uid=2,
            finished_at="2026-06-22T14:16:49+00:00",
            eval_run_id="live-13",
            score_challenger=0.55,
            score_king=0.45,
            win_margin=0.1,
            defeated_king_version=12,
        )
    ]

    merged = merge_king_histories(live, archived)
    versions = sorted(c.king_version for c in merged)
    assert versions == [12, 13]
    by_v = {c.king_version: c for c in merged}
    assert by_v[12].repo == "org/old"
    assert by_v[13].defeated_king_version == 12


def test_merge_king_histories_prefers_richer_live_row():
    archived = [
        AlbedoKingCoronation(
            king_version=20,
            model_uri="org/a@sha256:1",
            model_name="a",
            namespace="org",
            repo=None,
            coldkey=None,
            hotkey="hk",
            uid=1,
            finished_at="2026-06-25T10:00:00+00:00",
            eval_run_id="arch",
            score_challenger=0.6,
            score_king=0.4,
            win_margin=0.2,
        )
    ]
    live = [
        AlbedoKingCoronation(
            king_version=20,
            model_uri="org/a@sha256:1",
            model_name="a",
            namespace="org",
            repo="org/a",
            coldkey="ck1",
            hotkey="hk",
            uid=1,
            finished_at="2026-06-25T10:00:00+00:00",
            eval_run_id="live",
            score_challenger=0.6,
            score_king=0.4,
            win_margin=0.2,
        )
    ]

    merged = merge_king_histories(live, archived)
    assert len(merged) == 1
    assert merged[0].coldkey == "ck1"
    assert merged[0].repo == "org/a"
