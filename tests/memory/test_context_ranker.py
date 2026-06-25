"""Tests for deterministic context ranking."""

from __future__ import annotations

from src.memory.models import MemoryItem
from src.memory.rankers import extract_terms, rank_memory_item, semantic_relevance


def _item(text: str, source_type: str = "web", status: str = "active") -> MemoryItem:
    return MemoryItem(
        memory_type="evidence",
        text=text,
        source_type=source_type,  # type: ignore[arg-type]
        credibility_score=0.8,
        freshness_score=0.7,
        confidence=0.8,
        claim_type="evidence",
        status=status,  # type: ignore[arg-type]
    )


def test_extract_terms_handles_nested_subject() -> None:
    """Nested subject dictionaries produce searchable terms."""
    terms = extract_terms([{"company": "OpenAI", "product": "ChatGPT", "node": "CPU"}])

    assert {"openai", "chatgpt", "cpu"}.issubset(terms)


def test_semantic_relevance_uses_keyword_overlap() -> None:
    """Keyword overlap gives relevant items a positive score."""
    item = _item("OpenAI ChatGPT depends on Microsoft Azure cloud services.")

    score = semantic_relevance(item, {"openai", "chatgpt", "azure"})

    assert score > 0


def test_ranker_penalizes_rejected_memory() -> None:
    """Rejected memory gets a strong rejected penalty."""
    item = _item("OpenAI directly buys GPUs from NVIDIA.", status="rejected")

    candidate = rank_memory_item(item, subject_terms={"openai", "gpu"}, seen_hashes=set())

    assert candidate.rejected_memory_penalty == 1.0
    assert candidate.final_context_score < 0.5


def test_primary_source_gets_bonus() -> None:
    """Company, filing, and regulatory sources get a primary-source bonus."""
    item = _item("Company source confirms Azure dependency.", source_type="company")

    candidate = rank_memory_item(item, subject_terms={"azure"}, seen_hashes=set())

    assert candidate.primary_source_bonus == 1.0
