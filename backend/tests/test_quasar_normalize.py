"""Tests for Quasar dashboard normalization."""

from app.integrations.quasar_normalize import normalize_status, submission_counts


def test_submission_counts():
    subs = [
        {"status": "valid"},
        {"status": "valid"},
        {"status": "disqualified"},
        {"status": "king"},
    ]
    counts = submission_counts(subs)
    assert counts["valid"] == 2
    assert counts["disqualified"] == 1
    assert counts["king"] == 1


def test_normalize_status_king_and_phase():
    raw = {
        "king": {
            "uid": 172,
            "hf_repo": "user/model",
            "king_revision": "abc",
            "reign_number": 5,
        },
        "consensus_king": {"uid": 155, "support_fraction": 1.0, "block": 100},
        "state_king_uid": 172,
        "status": {
            "active": True,
            "phase": "precheck",
            "label": "Prechecking",
            "state_king_uid": 172,
            "chain_king_uid": 155,
            "weight_reveal_pending": True,
        },
        "submissions": [{"status": "valid"}],
        "queue": [],
        "policy": {"max_kl_threshold": 4.0},
    }
    out = normalize_status(raw)
    assert out["king"]["uid"] == 172
    assert out["consensus_king"]["uid"] == 155
    assert out["eval_phase"]["weight_reveal_pending"] is True
    assert out["submission_counts"]["valid"] == 1
    assert out["policy"]["max_kl_threshold"] == 4.0
