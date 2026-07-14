"""Tests for crown seed import."""

from app.services.albedo_king_history import missing_crown_versions
from app.services.albedo_crown_archive_service import coronations_from_seed_payload
from app.schemas.albedo_analysis import AlbedoKingCoronation


def test_missing_crown_versions_detects_v1_to_v12_gap():
    merged = [
        AlbedoKingCoronation(
            king_version=v,
            model_uri=f"org/m@v{v}",
            model_name="m",
            namespace="org",
            hotkey="hk",
            uid=1,
            finished_at="2026-06-22T00:00:00+00:00",
            eval_run_id=f"e{v}",
            score_challenger=0.6,
            score_king=0.4,
            win_margin=0.2,
        )
        for v in range(13, 17)
    ]
    missing = missing_crown_versions(merged)
    assert missing == list(range(1, 13))


def test_coronations_from_seed_payload():
    payload = {
        "coronations": [
            {
                "king_version": 5,
                "finished_at": "2026-05-10T08:00:00+00:00",
                "model_uri": "org/early@sha256:abc",
                "repo": "org/early",
                "coldkey": "ck5",
                "hotkey": "hk5",
                "uid": 9,
            }
        ]
    }
    rows = coronations_from_seed_payload(payload)
    assert len(rows) == 1
    assert rows[0].king_version == 5
    assert rows[0].repo == "org/early"
