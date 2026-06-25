"""Context selection policies for the v19 memory layer."""

from __future__ import annotations

from dataclasses import dataclass

PRIMARY_SOURCE_TYPES = {"filing", "company", "regulatory"}
CONTRADICTION_KEYWORDS = {"contradict", "counter", "however", "risk reduced", "not material"}


@dataclass(frozen=True)
class ContextSelectionPolicy:
    """Weights and limits for deterministic context selection."""

    version: str = "context-selection-v1"
    max_quote_chars: int = 600
    max_summary_chars: int = 300
    max_candidates: int = 50
    max_selected_items: int = 12
    chars_per_token: int = 4
    semantic_relevance_weight: float = 0.25
    source_credibility_weight: float = 0.20
    freshness_weight: float = 0.15
    graph_proximity_weight: float = 0.15
    evidence_diversity_weight: float = 0.10
    prior_success_weight: float = 0.10
    primary_source_bonus_weight: float = 0.10
    contradiction_bonus_weight: float = 0.10
    staleness_penalty_weight: float = 0.20
    duplicate_penalty_weight: float = 0.20
    rejected_memory_penalty_weight: float = 0.50


DEFAULT_CONTEXT_SELECTION_POLICY = ContextSelectionPolicy()


__all__ = [
    "CONTRADICTION_KEYWORDS",
    "DEFAULT_CONTEXT_SELECTION_POLICY",
    "PRIMARY_SOURCE_TYPES",
    "ContextSelectionPolicy",
]
