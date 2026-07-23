"""Short-lived in-memory cache for Hugging Face Hub latest search results."""

from __future__ import annotations

import time
from typing import Generic, TypeVar

T = TypeVar("T")

_DEFAULT_TTL_SECONDS = 180.0
_store: dict[str, tuple[float, object]] = {}


def cache_get(key: str, *, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> T | None:
    entry = _store.get(key)
    if entry is None:
        return None
    fetched_at, value = entry
    if time.monotonic() - fetched_at > ttl_seconds:
        _store.pop(key, None)
        return None
    return value  # type: ignore[return-value]


def cache_set(key: str, value: T) -> T:
    _store[key] = (time.monotonic(), value)
    return value


def cache_peek(key: str) -> T | None:
    entry = _store.get(key)
    if entry is None:
        return None
    return entry[1]  # type: ignore[return-value]
