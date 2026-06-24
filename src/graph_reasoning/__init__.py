"""v16 graph reasoning subsystem.

Re-exports the public surface so callers can do
``from src.graph_reasoning import GraphReasoningSubsystem``.
"""

from __future__ import annotations

from src.graph_reasoning.context_builder import build_graph_context
from src.graph_reasoning.evidence_binder import bind_evidence
from src.graph_reasoning.fixture_graph import EDGES as FIXTURE_EDGES
from src.graph_reasoning.fixture_graph import NODES as FIXTURE_NODES
from src.graph_reasoning.insight_validator import validate_all, validate_insight
from src.graph_reasoning.models import (
    CandidateGraphPath,
    EvidenceGraphPayload,
    GraphEdge,
    GraphEdgeMetadata,
    GraphInsightV16,
    GraphNode,
    GraphQueryContext,
)
from src.graph_reasoning.path_interpreter import interpret_paths
from src.graph_reasoning.path_retriever import (
    MIN_EDGE_CONFIDENCE,
    retrieve_candidate_paths,
)
from src.graph_reasoning.path_scorer import rank_paths, score_path
from src.graph_reasoning.subsystem import GraphReasoningSubsystem

__all__ = [
    "FIXTURE_EDGES",
    "FIXTURE_NODES",
    "MIN_EDGE_CONFIDENCE",
    "CandidateGraphPath",
    "EvidenceGraphPayload",
    "GraphEdge",
    "GraphEdgeMetadata",
    "GraphInsightV16",
    "GraphNode",
    "GraphQueryContext",
    "GraphReasoningSubsystem",
    "bind_evidence",
    "build_graph_context",
    "interpret_paths",
    "rank_paths",
    "retrieve_candidate_paths",
    "score_path",
    "validate_all",
    "validate_insight",
]
