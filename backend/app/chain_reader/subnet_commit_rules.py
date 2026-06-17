"""Per-subnet model commitment rules — SN97 Albedo (v6 only) vs SN24 Quasar (JSON)."""

from __future__ import annotations

QUASAR_NETUID = 24
ALBEDO_NETUID = 97

# Albedo SN97: v6 pipe only. v5, legacy JSON, and other formats are ignored.
ALBEDO_MODEL_VERSIONS = frozenset({"v6"})

# Quasar SN24: JSON model commits (stored as quasar; json kept for legacy rows).
QUASAR_JSON_VERSIONS = frozenset({"quasar", "json"})


def model_versions_for_subnet(netuid: int) -> frozenset[str]:
    if netuid == QUASAR_NETUID:
        return QUASAR_JSON_VERSIONS
    return ALBEDO_MODEL_VERSIONS


def model_versions_sql_tuple(netuid: int) -> tuple[str, ...]:
    return tuple(sorted(model_versions_for_subnet(netuid)))


def is_albedo_subnet(netuid: int) -> bool:
    return netuid != QUASAR_NETUID


def normalize_stored_version(version: str | None, netuid: int) -> str | None:
    """Map stored labels to canonical version for a subnet."""
    if not version:
        return None
    if netuid == QUASAR_NETUID:
        if version == "json":
            return "quasar"
        return version if version in QUASAR_JSON_VERSIONS else None
    if version != "v6":
        return None
    return "v6"


def is_published_slot_type(commitment_type: str, netuid: int) -> bool:
    """Whether a slot has a current model publish for this subnet."""
    if netuid == QUASAR_NETUID:
        return commitment_type in ("v5", "v6", "json")
    return commitment_type == "v6"


def is_v6_history_row(reveal_string: str, commit_payload: dict | None) -> bool:
    """True if a CommitmentHistory row is a v6 pipe commit."""
    if reveal_string.startswith("v6|"):
        return True
    if commit_payload and commit_payload.get("version") == "v6":
        return True
    return False
