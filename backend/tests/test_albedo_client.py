"""Albedo dashboard client helpers."""

from app.integrations.albedo_client import king_hotkey, king_uid


def test_king_hotkey_from_dashboard():
    dashboard = {"king": {"hotkey": "5Gy9xtKFvLcYk6U282Fb1wEM2LnCFkFSCEAEwXAh7MTaRPdi", "uid": 93}}
    assert king_hotkey(dashboard) == "5Gy9xtKFvLcYk6U282Fb1wEM2LnCFkFSCEAEwXAh7MTaRPdi"
    assert king_uid(dashboard) == 93


def test_king_helpers_empty():
    assert king_hotkey(None) is None
    assert king_uid({}) is None
