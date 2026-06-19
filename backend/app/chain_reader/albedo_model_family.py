"""Infer Albedo SN97 competition era from Hippius repo names.

Validators may run ahead of the public `chain.toml` on main — e.g. Qwen3.6-35B
commits use `namespace/albedo-qwen3.6-35b-*` while GitHub still documents 4B.
"""

from __future__ import annotations

import re

# Canonical Albedo repo prefixes (mirror expected chain.toml repo_pattern values).
_ALBEDO_QWEN36_35B = re.compile(r"^[^/]+/albedo-qwen3\.6-35b(?:-.+)?$", re.IGNORECASE)
_ALBEDO_QWEN3_4B = re.compile(r"^[^/]+/albedo-qwen3-4b(?:-.+)?$", re.IGNORECASE)

# Loose hints when miners use non-standard but readable repo ids.
_QWEN36_35B_HINT = re.compile(r"qwen3\.6[-_.]?35b|albedo-qwen3\.6", re.IGNORECASE)
_QWEN3_4B_HINT = re.compile(r"qwen3[-_]4b|albedo-qwen3-4b", re.IGNORECASE)

FAMILY_QWEN36_35B = "qwen3.6-35b"
FAMILY_QWEN3_4B = "qwen3-4b"

ALBEDO_MODEL_FAMILIES: tuple[str, ...] = (FAMILY_QWEN36_35B, FAMILY_QWEN3_4B)


def infer_albedo_model_family(repo: str | None) -> str | None:
    """Return competition family id from a Hippius repo path, or None if unknown."""
    if not repo or "/" not in repo:
        return None
    text = repo.strip()
    if _ALBEDO_QWEN36_35B.match(text) or _QWEN36_35B_HINT.search(text):
        return FAMILY_QWEN36_35B
    if _ALBEDO_QWEN3_4B.match(text) or _QWEN3_4B_HINT.search(text):
        return FAMILY_QWEN3_4B
    return None


def repo_from_slot_detail(detail: str | None, commitment_type: str | None) -> str | None:
    """Slot `detail` is the repo for published v6/v7 pipe commits."""
    if not detail or "/" not in detail:
        return None
    if commitment_type in ("v6", "v7"):
        return detail
    return None
