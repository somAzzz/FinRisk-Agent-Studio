"""Validated memory ingestion helpers."""

from __future__ import annotations

from src.evaluation.memory_guardrails import MemoryWriteGuardrails
from src.memory.models import MemoryItem, MemoryWriteDecision
from src.memory.store import MemoryStore


class MemoryIngestor:
    """Apply write guardrails and persist MemoryItem rows."""

    def __init__(
        self,
        store: MemoryStore,
        guardrails: MemoryWriteGuardrails | None = None,
    ):
        self.store = store
        self.guardrails = guardrails or MemoryWriteGuardrails()

    def ingest(self, item: MemoryItem) -> tuple[MemoryWriteDecision, MemoryItem | None]:
        """Validate and store a memory item."""
        decision = self.guardrails.validate(item)
        if not decision.allowed:
            return decision, None
        if decision.target_status is not None and item.status != decision.target_status:
            item = item.model_copy(update={"status": decision.target_status})
        stored = self.store.upsert(item)
        return decision, stored


__all__ = ["MemoryIngestor"]
