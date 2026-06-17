"""Albedo dashboard client helpers."""

from app.integrations.albedo_client import king_hotkey, king_uid
from app.integrations.albedo_normalize import current_king, normalize_dashboard


def test_king_from_v2_reign():
    raw = {
        "eval_runs": [],
        "reign": {
            "members": [
                {"king_version": 29, "hotkey": "hk-old", "uid": 1},
                {"king_version": 30, "hotkey": "hk-new", "uid": 161},
            ]
        },
    }
    norm = normalize_dashboard(raw)
    assert king_hotkey(norm) == "hk-new"
    assert king_uid(norm) == 161
    assert current_king(norm["reign"])["king_version"] == 30


def test_king_helpers_empty():
    assert king_hotkey(None) is None
    assert king_uid({}) is None
