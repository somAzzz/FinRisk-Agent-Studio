"""Lifecycle helpers for v19 memory items."""

from __future__ import annotations

from src.memory.models import MemoryItem, MemoryStatus, utcnow

UNUSABLE_STATUSES: set[MemoryStatus] = {"rejected", "deprecated"}
CONTEXT_WARNING_STATUSES: set[MemoryStatus] = {"stale", "superseded"}


def can_enter_context(item: MemoryItem) -> bool:
    """Return True when a memory item may be considered for ContextPack selection."""
    return item.status not in UNUSABLE_STATUSES


def can_support_factual_claim(item: MemoryItem) -> bool:
    """Return True when an item can support a final factual claim."""
    if item.status not in {"active", "used", "validated"}:
        return False
    if item.claim_type != "evidence":
        return False
    return item.memory_type in {"evidence", "graph_edge"}


def mark_used(item: MemoryItem) -> MemoryItem:
    """Return a copy of ``item`` marked as used."""
    return item.model_copy(update={"status": "used", "last_used_at": utcnow()})


def transition(item: MemoryItem, status: MemoryStatus) -> MemoryItem:
    """Return a copy of ``item`` with a new lifecycle status."""
    updates = {"status": status, "last_seen_at": utcnow()}
    return item.model_copy(update=updates)


__all__ = [
    "CONTEXT_WARNING_STATUSES",
    "UNUSABLE_STATUSES",
    "can_enter_context",
    "can_support_factual_claim",
    "mark_used",
    "transition",
]
