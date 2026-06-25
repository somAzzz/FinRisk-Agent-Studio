"""Tests for validated memory ingestion."""

from __future__ import annotations

from src.memory.ingestion import MemoryIngestor
from src.memory.models import MemoryItem
from src.memory.store import MemoryStore


def test_ingestor_applies_guardrail_target_status(tmp_path) -> None:
    """MemoryIngestor applies guardrail status downgrades before persistence."""
    store = MemoryStore(cache_dir=tmp_path)
    ingestor = MemoryIngestor(store)
    item = MemoryItem(
        memory_type="evidence",
        text="NVIDIA supplies AI accelerators.",
        source_type="web",
        source_url="https://example.com",
        credibility_score=0.8,
        freshness_score=0.9,
        confidence=0.8,
        claim_type="evidence",
        status="active",
    )

    decision, stored = ingestor.ingest(item)

    assert decision.allowed is True
    assert decision.target_status == "candidate"
    assert stored is not None
    assert stored.status == "candidate"
    assert store.get(stored.memory_id).status == "candidate"  # type: ignore[union-attr]


def test_ingestor_does_not_persist_blocked_memory(tmp_path) -> None:
    """Blocked memory is not persisted."""
    store = MemoryStore(cache_dir=tmp_path)
    ingestor = MemoryIngestor(store)
    item = MemoryItem(
        memory_type="domain_prior",
        text="AI data centers use electricity.",
        source_type="domain_prior",
        credibility_score=0.4,
        freshness_score=0.5,
        confidence=0.4,
        claim_type="evidence",
        status="active",
    )

    decision, stored = ingestor.ingest(item)

    assert decision.allowed is False
    assert stored is None
    assert store.get(item.memory_id) is None
