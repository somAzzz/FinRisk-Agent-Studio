"""Cycle-safe public surface for the v16 graph reasoning subsystem."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS: dict[str, tuple[str, str]] = {
    "FIXTURE_EDGES": ("src.graph_reasoning.fixture_graph", "EDGES"),
    "FIXTURE_NODES": ("src.graph_reasoning.fixture_graph", "NODES"),
    "MIN_EDGE_CONFIDENCE": (
        "src.graph_reasoning.path_retriever",
        "MIN_EDGE_CONFIDENCE",
    ),
    "CandidateGraphPath": ("src.graph_reasoning.models", "CandidateGraphPath"),
    "EvidenceGraphPayload": ("src.graph_reasoning.models", "EvidenceGraphPayload"),
    "GraphEdge": ("src.graph_reasoning.models", "GraphEdge"),
    "GraphEdgeMetadata": ("src.graph_reasoning.models", "GraphEdgeMetadata"),
    "GraphInsightV16": ("src.graph_reasoning.models", "GraphInsightV16"),
    "GraphNode": ("src.graph_reasoning.models", "GraphNode"),
    "GraphQueryContext": ("src.graph_reasoning.models", "GraphQueryContext"),
    "GraphReasoningSubsystem": (
        "src.graph_reasoning.subsystem",
        "GraphReasoningSubsystem",
    ),
    "bind_evidence": ("src.graph_reasoning.evidence_binder", "bind_evidence"),
    "build_graph_context": (
        "src.graph_reasoning.context_builder",
        "build_graph_context",
    ),
    "interpret_paths": ("src.graph_reasoning.path_interpreter", "interpret_paths"),
    "rank_paths": ("src.graph_reasoning.path_scorer", "rank_paths"),
    "retrieve_candidate_paths": (
        "src.graph_reasoning.path_retriever",
        "retrieve_candidate_paths",
    ),
    "score_path": ("src.graph_reasoning.path_scorer", "score_path"),
    "validate_all": ("src.graph_reasoning.insight_validator", "validate_all"),
    "validate_insight": (
        "src.graph_reasoning.insight_validator",
        "validate_insight",
    ),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
