"""Tests for v19 memory models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.memory.models import MemoryItem, stable_memory_hash


def test_memory_item_derives_stable_hash() -> None:
    """MemoryItem computes a deterministic hash when omitted."""
    item = MemoryItem(
        memory_type="evidence",
        text="NVIDIA supplies AI accelerators for data centers.",
        source_type="web",
        source_url="https://example.com/nvidia",
        credibility_score=0.7,
        freshness_score=0.8,
        confidence=0.75,
        claim_type="evidence",
        status="active",
    )

    assert item.hash == stable_memory_hash(
        text=item.text,
        source_type=item.source_type,
        source_url=item.source_url,
        memory_type=item.memory_type,
    )


def test_memory_item_rejects_empty_text() -> None:
    """Empty memory text is invalid because memory must be auditable."""
    with pytest.raises(ValidationError):
        MemoryItem(
            memory_type="evidence",
            text=" ",
            source_type="web",
            credibility_score=0.7,
            freshness_score=0.8,
            confidence=0.75,
            claim_type="evidence",
        )


def test_score_ranges_are_validated() -> None:
    """Scores must be bounded to keep ranking deterministic."""
    with pytest.raises(ValidationError):
        MemoryItem(
            memory_type="evidence",
            text="Evidence",
            source_type="web",
            credibility_score=1.5,
            freshness_score=0.8,
            confidence=0.75,
            claim_type="evidence",
        )
