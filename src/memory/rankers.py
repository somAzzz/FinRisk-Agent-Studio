"""Deterministic context ranking for memory candidates."""

from __future__ import annotations

import re
from collections.abc import Iterable

from src.memory.lifecycle import can_enter_context
from src.memory.models import ContextCandidate, MemoryItem
from src.memory.policies import (
    CONTRADICTION_KEYWORDS,
    DEFAULT_CONTEXT_SELECTION_POLICY,
    PRIMARY_SOURCE_TYPES,
    ContextSelectionPolicy,
)

TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_\-]+")


def extract_terms(values: Iterable[object]) -> set[str]:
    """Extract lowercase matching terms from arbitrary values."""
    terms: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            terms.update(extract_terms(value.values()))
            continue
        if isinstance(value, (list, tuple, set)):
            terms.update(extract_terms(value))
            continue
        text = str(value).lower()
        terms.update(match.group(0) for match in TOKEN_RE.finditer(text))
    return terms


def semantic_relevance(item: MemoryItem, terms: set[str]) -> float:
    """Score keyword/entity overlap in the 0..1 range."""
    if not terms:
        return 0.0
    haystack = extract_terms(
        [
            item.text,
            item.summary or "",
            item.source_title or "",
            item.entities,
            item.tickers,
            item.products,
            item.risks,
        ]
    )
    if not haystack:
        return 0.0
    overlap = len(terms & haystack)
    return min(1.0, overlap / max(1, min(len(terms), 8)))


def rank_memory_item(
    item: MemoryItem,
    *,
    subject_terms: set[str],
    seen_hashes: set[str] | None = None,
    policy: ContextSelectionPolicy = DEFAULT_CONTEXT_SELECTION_POLICY,
) -> ContextCandidate:
    """Rank one memory item according to the v19 deterministic policy."""
    relevance = semantic_relevance(item, subject_terms)
    graph_proximity = 1.0 if item.memory_type == "graph_edge" and relevance > 0 else 0.0
    diversity = 1.0
    duplicate_penalty = 1.0 if seen_hashes is not None and item.hash in seen_hashes else 0.0
    staleness_penalty = 1.0 if item.status == "stale" else 0.0
    rejected_penalty = 1.0 if not can_enter_context(item) else 0.0
    primary_bonus = 1.0 if item.source_type in PRIMARY_SOURCE_TYPES else 0.0
    text_l = f"{item.text} {item.summary or ''}".lower()
    contradiction_bonus = 1.0 if any(k in text_l for k in CONTRADICTION_KEYWORDS) else 0.0
    prior_success = 0.5 if item.memory_type == "episode" else 0.0

    score = (
        policy.semantic_relevance_weight * relevance
        + policy.source_credibility_weight * item.credibility_score
        + policy.freshness_weight * item.freshness_score
        + policy.graph_proximity_weight * graph_proximity
        + policy.evidence_diversity_weight * diversity
        + policy.prior_success_weight * prior_success
        + policy.primary_source_bonus_weight * primary_bonus
        + policy.contradiction_bonus_weight * contradiction_bonus
        - policy.staleness_penalty_weight * staleness_penalty
        - policy.duplicate_penalty_weight * duplicate_penalty
        - policy.rejected_memory_penalty_weight * rejected_penalty
    )

    return ContextCandidate(
        memory_id=item.memory_id,
        reason_selected="ranked_by_context_selection_v1",
        semantic_relevance=relevance,
        source_credibility=item.credibility_score,
        freshness=item.freshness_score,
        graph_proximity=graph_proximity,
        diversity_contribution=diversity,
        prior_success_score=prior_success,
        primary_source_bonus=primary_bonus,
        contradiction_bonus=contradiction_bonus,
        duplicate_penalty=duplicate_penalty,
        staleness_penalty=staleness_penalty,
        rejected_memory_penalty=rejected_penalty,
        final_context_score=score,
    )


__all__ = ["extract_terms", "rank_memory_item", "semantic_relevance"]
