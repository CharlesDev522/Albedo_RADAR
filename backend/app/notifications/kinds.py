"""Alert kinds surfaced to Slack."""

from __future__ import annotations

from typing import Literal

AlertKind = Literal[
    "crown_won",
    "crown_lost",
    "duel_new",
    "king_defended",
    "slot_new",
    "slot_changed",
    "commit_new",
    "commit_updated",
    "repo_new",
    "repo_updated",
    "reg_fee_low",
]

SEVERITY: dict[AlertKind, str] = {
    "crown_won": "critical",
    "crown_lost": "critical",
    "duel_new": "high",
    "king_defended": "high",
    "slot_new": "high",
    "slot_changed": "medium",
    "commit_new": "high",
    "commit_updated": "medium",
    "repo_new": "high",
    "repo_updated": "medium",
    "reg_fee_low": "high",
}

SLACK_EMOJI: dict[AlertKind, str] = {
    "crown_won": ":crown:",
    "crown_lost": ":skull:",
    "duel_new": ":crossed_swords:",
    "king_defended": ":shield:",
    "slot_new": ":slot_machine:",
    "slot_changed": ":arrows_counterclockwise:",
    "commit_new": ":link:",
    "commit_updated": ":pencil2:",
    "repo_new": ":package:",
    "repo_updated": ":cloud:",
    "reg_fee_low": ":money_with_wings:",
}
