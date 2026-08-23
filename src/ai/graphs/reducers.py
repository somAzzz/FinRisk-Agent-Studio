"""Deterministic reducers for future safe graph fan-out branches."""

from __future__ import annotations

from collections.abc import Callable, Iterable


def merge_unique_sorted[T](
    branches: Iterable[Iterable[T]],
    *,
    key: Callable[[T], str],
) -> list[T]:
    """Merge successful branch rows idempotently with stable ordering."""
    merged: dict[str, T] = {}
    for branch in branches:
        for item in branch:
            merged.setdefault(key(item), item)
    return [merged[item_key] for item_key in sorted(merged)]


__all__ = ["merge_unique_sorted"]
