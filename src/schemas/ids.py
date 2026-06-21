"""Stable identifier helpers for FinText-LLM schemas."""

from __future__ import annotations

import hashlib


def stable_id(prefix: str, *parts: str) -> str:
    """Return a deterministic id derived from a prefix and ordered parts.

    The id has the form ``"{prefix}_{sha1[:12]}"``. Identical inputs always
    produce the same id, which keeps cross-run and cross-process references
    stable for downstream storage layers (DuckDB, Neo4j, etc.).
    """
    raw = "|".join((prefix, *parts))
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"
