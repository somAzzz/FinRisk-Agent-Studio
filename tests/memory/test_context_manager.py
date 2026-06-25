"""Tests for ContextManager."""

from __future__ import annotations

from src.memory import ContextManager, MemoryItem, MemoryStore


def _memory(
    text: str,
    *,
    status: str = "active",
    claim_type: str = "evidence",
    source_type: str = "web",
    credibility: float = 0.8,
    freshness: float = 0.8,
) -> MemoryItem:
    return MemoryItem(
        memory_type="evidence",
        text=text,
        summary=text,
        source_type=source_type,  # type: ignore[arg-type]
        entities=["OpenAI"],
        products=["ChatGPT"],
        credibility_score=credibility,
        freshness_score=freshness,
        confidence=0.8,
        claim_type=claim_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
    )


def test_context_manager_selects_relevant_memory(tmp_path) -> None:
    """Relevant memory enters selected evidence."""
    store = MemoryStore(cache_dir=tmp_path)
    item = store.upsert(_memory("OpenAI ChatGPT uses Microsoft Azure cloud infrastructure."))
    manager = ContextManager(store)

    pack = manager.build(
        run_id="run-1",
        step_name="supplier_discovery",
        task="find cloud suppliers",
        subject={"company": "OpenAI", "product": "ChatGPT", "node": "cloud"},
        intent="supplier_discovery",
    )

    assert item.memory_id in pack.selected_memory_ids
    assert pack.selected_evidence[0].memory_id == item.memory_id


def test_context_manager_excludes_rejected_memory_and_records_negative_memory(tmp_path) -> None:
    """Rejected claim memory is excluded but available as negative memory."""
    store = MemoryStore(cache_dir=tmp_path)
    rejected = store.upsert(
        MemoryItem(
            memory_type="claim",
            text="OpenAI directly buys GPUs from NVIDIA.",
            source_type="human_feedback",
            entities=["OpenAI", "NVIDIA"],
            products=["ChatGPT"],
            credibility_score=1.0,
            freshness_score=1.0,
            confidence=1.0,
            claim_type="inference",
            status="rejected",
        )
    )
    manager = ContextManager(store)

    pack = manager.build(
        run_id="run-1",
        step_name="supplier_discovery",
        task="find GPU suppliers",
        subject={"company": "OpenAI", "product": "ChatGPT", "node": "gpu"},
        intent="supplier_discovery",
    )

    assert rejected.memory_id not in pack.selected_memory_ids
    assert rejected.memory_id in pack.rejected_memory_ids
    assert pack.negative_memory == [rejected.text]


def test_context_manager_warns_on_stale_and_hypothesis(tmp_path) -> None:
    """Stale and hypothesis memory are selected only with warnings."""
    store = MemoryStore(cache_dir=tmp_path)
    stale = store.upsert(_memory("Older Azure evidence.", status="stale"))
    hypothesis = store.upsert(
        _memory("CPU supply chain may involve Intel.", claim_type="hypothesis")
    )
    manager = ContextManager(store)

    pack = manager.build(
        run_id="run-1",
        step_name="supplier_discovery",
        task="find CPU suppliers",
        subject={"company": "OpenAI", "product": "ChatGPT", "node": "CPU"},
        intent="supplier_discovery",
    )

    assert stale.memory_id in pack.selected_memory_ids
    assert hypothesis.memory_id in pack.selected_memory_ids
    assert any("stale memory selected" in warning for warning in pack.warnings)
    assert any("hypothesis memory selected" in warning for warning in pack.warnings)


def test_context_manager_respects_token_budget(tmp_path) -> None:
    """Low token budget rejects otherwise relevant memory."""
    store = MemoryStore(cache_dir=tmp_path)
    first = store.upsert(_memory("OpenAI ChatGPT Azure " * 30))
    second = store.upsert(_memory("OpenAI ChatGPT GPU NVIDIA " * 30))
    manager = ContextManager(store)

    pack = manager.build(
        run_id="run-1",
        step_name="supplier_discovery",
        task="find suppliers",
        subject={"company": "OpenAI", "product": "ChatGPT"},
        intent="supplier_discovery",
        token_budget=10,
    )

    assert len(pack.selected_memory_ids) < 2
    assert {first.memory_id, second.memory_id}.intersection(pack.rejected_memory_ids)
