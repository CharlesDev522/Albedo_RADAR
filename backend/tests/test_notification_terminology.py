"""Tests for notification terminology helpers."""

from app.notifications.terminology import prose_for, title_for


def test_slot_title_uses_publish_not_buy():
    title = title_for("slot_new", 97, {"uid": 42, "commitment_type": "v7"})
    assert "published v7 commitment" in title
    assert "bought" not in title.lower()


def test_commit_updated_title():
    title = title_for(
        "commit_updated",
        97,
        {"uid": 166, "repo": "ns/model"},
    )
    assert "changed CommitmentOf" in title


def test_crown_won_prose_includes_judge_scores():
    prose = prose_for(
        "crown_won",
        "SN97 crowned",
        {
            "repo": "cyantest/model",
            "uid": 5,
            "score_challenger": 0.62,
            "score_king": 0.38,
            "win_margin": 0.24,
            "judge_scores": [
                {
                    "judge": "glm",
                    "challenger_score": 0.65,
                    "king_score": 0.35,
                    "pick_challenger": True,
                },
                {
                    "judge": "qwen3.5-397b-a17b",
                    "challenger_score": 0.59,
                    "king_score": 0.41,
                    "pick_challenger": True,
                },
            ],
        },
    )
    assert "Total:" in prose
    assert "62.0%" in prose
    assert "Judges:" in prose
    assert "*glm:*" in prose
    assert "→ ch" in prose
