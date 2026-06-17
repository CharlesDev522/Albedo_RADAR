"""Albedo normalize and analytics tests."""

from app.integrations.albedo_normalize import (
    build_hf_analytics,
    hf_account,
    king_title_name,
    model_repo,
    normalize_dashboard,
    verdict_info,
)


def test_king_title_name():
    assert king_title_name(30) == "ALBEDO-XXX"
    assert king_title_name(1) == "ALBEDO-I"


def test_model_repo_strips_digest():
    uri = "allforone1l1/albedo-qwen3-4b-test@sha256:abc"
    assert model_repo(uri) == "allforone1l1/albedo-qwen3-4b-test"
    assert hf_account(uri) == "allforone1l1"


def test_verdict_badges():
    assert verdict_info({"challenger_won": True, "coronated": True})["badge"] == "crowned"
    assert verdict_info({"challenger_won": True, "coronated": False})["badge"] == "won"
    assert verdict_info({"challenger_won": False})["badge"] == "lost"


def test_hf_analytics_dethrones():
    normalized = normalize_dashboard(
        {
            "eval_runs": [
                {
                    "eval_run_id": "a",
                    "model_uri": "winner/a@sha256:x",
                    "hotkey": "hk1",
                    "challenger_won": True,
                    "coronated": True,
                    "king_version": 2,
                    "king": {"model_uri": "loser/b@sha256:y", "hotkey": "hk2"},
                },
                {
                    "eval_run_id": "b",
                    "model_uri": "loser/b@sha256:y",
                    "hotkey": "hk2",
                    "challenger_won": False,
                    "coronated": False,
                },
            ],
            "reign": {"members": []},
        }
    )
    stats = build_hf_analytics(normalized)
    by_name = {a["hf_account"]: a for a in stats["accounts"]}
    assert by_name["winner"]["crowns"] == 1
    assert by_name["winner"]["dethrones_caused"] == 1
    assert by_name["loser"]["times_dethroned"] == 1
    assert by_name["loser"]["challenges"] == 1
