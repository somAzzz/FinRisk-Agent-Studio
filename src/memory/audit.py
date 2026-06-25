"""Audit helpers for context packs."""

from __future__ import annotations

from src.memory.models import ContextPack


def context_manifest_complete(pack: ContextPack) -> bool:
    """Return True when selected ids and evidence references are consistent."""
    evidence_ids = {item.memory_id for item in pack.selected_evidence}
    return evidence_ids == set(pack.selected_memory_ids)


__all__ = ["context_manifest_complete"]
