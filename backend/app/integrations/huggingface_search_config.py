"""Shared Hugging Face Hub search configuration for discovery and latest panels."""

from __future__ import annotations

HF_DISCOVERY_QUERIES: tuple[str, ...] = ("albedo-qwen3.6-35b", "albedo-qwen3-4b")

HF_SORT_CREATED_AT = "createdAt"
HF_SORT_LAST_MODIFIED = "lastModified"
HF_SORT_DOWNLOADS = "downloads"
HF_SORT_LIKES = "likes"

HF_SORT_OPTIONS: tuple[tuple[str, str], ...] = (
    (HF_SORT_CREATED_AT, "Recently created"),
    (HF_SORT_LAST_MODIFIED, "Recently updated"),
    (HF_SORT_DOWNLOADS, "Most downloads"),
    (HF_SORT_LIKES, "Most likes"),
)

HF_DEFAULT_TAG_OPTIONS: tuple[str, ...] = (
    "safetensors",
    "qwen3_5_moe",
    "transformers",
    "pytorch",
)

VALID_HF_SORTS: frozenset[str] = frozenset(key for key, _label in HF_SORT_OPTIONS)
