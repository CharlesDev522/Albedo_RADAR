"""SN97 Albedo model commitment rules."""

from __future__ import annotations

ALBEDO_NETUID = 97

# Albedo SN97: accept v6/v7 pipe wire formats; competition era comes from repo name.
ALBEDO_PIPE_VERSIONS = frozenset({"v6", "v7"})

# Backwards-compatible alias used by DB filters and poller.
ALBEDO_MODEL_VERSIONS = ALBEDO_PIPE_VERSIONS

LEGACY_PIPE_VERSIONS = frozenset({"v5", "v6", "v7"})


def model_versions_for_subnet(netuid: int) -> frozenset[str]:
    return ALBEDO_PIPE_VERSIONS


def model_versions_sql_tuple(netuid: int) -> tuple[str, ...]:
    return tuple(sorted(model_versions_for_subnet(netuid)))


def is_albedo_subnet(netuid: int) -> bool:
    return True


def is_albedo_pipe_version(version: str | None) -> bool:
    return bool(version and version in ALBEDO_PIPE_VERSIONS)


def pipe_version_from_reveal(reveal_string: str) -> str | None:
    """Extract pipe version prefix (e.g. v6, v7) from a reveal string."""
    if not reveal_string or "|" not in reveal_string:
        return None
    version = reveal_string.split("|", 1)[0]
    return version if version.startswith("v") else None


def normalize_stored_version(version: str | None, netuid: int) -> str | None:
    """Map stored labels to canonical version for SN97."""
    if not version:
        return None
    return version if version in ALBEDO_PIPE_VERSIONS else None


def is_published_slot_type(commitment_type: str, netuid: int) -> bool:
    """Whether a slot has a current model publish on SN97."""
    return commitment_type in ALBEDO_PIPE_VERSIONS


def is_albedo_pipe_history_row(reveal_string: str, commit_payload: dict | None) -> bool:
    """True if a CommitmentHistory row is a v6/v7 Albedo pipe commit."""
    version = pipe_version_from_reveal(reveal_string)
    if version in ALBEDO_PIPE_VERSIONS:
        return True
    if commit_payload and commit_payload.get("version") in ALBEDO_PIPE_VERSIONS:
        return True
    return False


# Backwards-compatible alias
is_v6_history_row = is_albedo_pipe_history_row
