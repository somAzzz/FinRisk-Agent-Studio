"""Tests for the v19 SQLite memory store."""

from __future__ import annotations

from src.memory.models import MemoryItem
from src.memory.store import MemoryStore


def _item(text: str = "Microsoft Azure provides cloud infrastructure.") -> MemoryItem:
    return MemoryItem(
        memory_type="evidence",
        text=text,
        summary="Azure infrastructure evidence.",
        source_type="company",
        source_url="https://example.com/azure",
        entities=["Microsoft Azure"],
        products=["ChatGPT"],
        credibility_score=0.9,
        freshness_score=0.8,
        confidence=0.85,
        claim_type="evidence",
        status="active",
        provenance={"run_id": "run-1"},
    )


def test_store_upsert_and_get(tmp_path) -> None:
    """MemoryStore persists and retrieves a memory item."""
    store = MemoryStore(cache_dir=tmp_path)
    stored = store.upsert(_item())

    loaded = store.get(stored.memory_id)

    assert loaded is not None
    assert loaded.memory_id == stored.memory_id
    assert loaded.text == stored.text


def test_store_dedupes_by_hash(tmp_path) -> None:
    """A duplicate hash preserves the first memory id."""
    store = MemoryStore(cache_dir=tmp_path)
    first = store.upsert(_item())
    duplicate = _item()
    duplicate.memory_id = "different-id"

    second = store.upsert(duplicate)

    assert second.memory_id == first.memory_id


def test_store_status_transitions(tmp_path) -> None:
    """Store can mark items as stale, rejected, and used."""
    store = MemoryStore(cache_dir=tmp_path)
    stored = store.upsert(_item())

    stale = store.mark_stale(stored.memory_id, "old evidence")
    rejected = store.mark_rejected(stored.memory_id, "bad relation")
    used = store.mark_used(stored.memory_id)

    assert stale is not None
    assert stale.status == "stale"
    assert rejected is not None
    assert rejected.status == "rejected"
    assert used is not None
    assert used.status == "used"


def test_search_candidates_excludes_rejected_by_default(tmp_path) -> None:
    """Rejected memory is hidden from default candidate search."""
    store = MemoryStore(cache_dir=tmp_path)
    stored = store.upsert(_item())
    store.mark_rejected(stored.memory_id, "incorrect")

    candidates = store.search_candidates(subject={"product": "ChatGPT"})

    assert candidates == []


def test_list_by_entity_and_run(tmp_path) -> None:
    """Entity and run lookup support workflow integration."""
    store = MemoryStore(cache_dir=tmp_path)
    stored = store.upsert(_item())

    assert [item.memory_id for item in store.list_by_entity("Azure")] == [stored.memory_id]
    assert [item.memory_id for item in store.list_by_run("run-1")] == [stored.memory_id]
