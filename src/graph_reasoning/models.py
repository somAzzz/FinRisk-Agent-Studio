"""v16 graph reasoning models.

The v16 spec splits the v15 ``GraphReasonerStep`` into a 6-stage
pipeline (context builder, path retriever, path scorer, evidence
binder, path interpreter, insight validator). Each stage is a
small Pydantic-friendly module and operates on the models defined
in this file.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.workflows.state import utcnow


NodeType = Literal[
    "Company",
    "Ticker",
    "Filing",
    "Risk",
    "Evidence",
    "Claim",
    "Supplier",
    "Sector",
    "Region",
    "Policy",
    "MacroFactor",
    "Event",
    "Opportunity",
]

EdgeExtractionMethod = Literal["rule", "llm", "manual", "imported"]

InsightType = Literal[
    "second_order_risk",
    "supply_chain_exposure",
    "policy_transmission",
    "market_opportunity",
    "research_hypothesis",
]


# ---------------------------------------------------------------------------
# Nodes & edges
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: NodeType
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_method: EdgeExtractionMethod = "rule"
    created_at: datetime = Field(default_factory=utcnow)


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str = Field(default_factory=lambda: f"e-{uuid.uuid4().hex[:8]}")
    source_node_id: str
    target_node_id: str
    edge_type: str
    metadata: GraphEdgeMetadata


# ---------------------------------------------------------------------------
# Query / path
# ---------------------------------------------------------------------------


class GraphQueryContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: str
    ticker: str
    risk_ids: list[str] = Field(default_factory=list)
    focus_entities: list[str] = Field(default_factory=list)
    focus_risk_types: list[str] = Field(default_factory=list)
    max_hops: int = Field(default=3, ge=1, le=4)
    allowed_edge_types: list[str] = Field(default_factory=list)


class CandidateGraphPath(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path_id: str = Field(default_factory=lambda: f"p-{uuid.uuid4().hex[:8]}")
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    path_text: str
    evidence_ids: list[str] = Field(default_factory=list)
    hop_count: int = Field(ge=1, le=4)
    path_score: float | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Insight
# ---------------------------------------------------------------------------


class GraphInsightV16(BaseModel):
    model_config = ConfigDict(extra="forbid")

    insight_id: str = Field(default_factory=lambda: f"ins-{uuid.uuid4().hex[:8]}")
    source_company: str
    insight_type: InsightType
    risk_path_ids: list[str] = Field(default_factory=list)
    affected_entities: list[str] = Field(default_factory=list)
    explanation: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    uncertainty: str = ""
    recommended_next_questions: list[str] = Field(default_factory=list)
    research_theme: str | None = None


class EvidenceGraphPayload(BaseModel):
    """Single payload the frontend's Evidence Graph tab consumes."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    paths: list[CandidateGraphPath] = Field(default_factory=list)
    insights: list[GraphInsightV16] = Field(default_factory=list)
    guardrail_findings: list[dict] = Field(default_factory=list)


__all__ = [
    "CandidateGraphPath",
    "EdgeExtractionMethod",
    "EvidenceGraphPayload",
    "GraphEdge",
    "GraphEdgeMetadata",
    "GraphInsightV16",
    "GraphNode",
    "GraphQueryContext",
    "InsightType",
    "NodeType",
]
