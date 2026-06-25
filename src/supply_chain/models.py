"""v18 Pydantic schemas for the product supply chain explorer.

The schemas in this module are the single source of truth for the
Sankey payload, the workflow state, and the recursive-expansion
request. Validation is intentionally strict (``extra="forbid"``)
because the v18 frontend deserialises the JSON verbatim and any
unknown field would silently drift the contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.workflows.state import utcnow

NodeType = Literal[
    "company",
    "product",
    "component",
    "service",
    "commodity",
    "infrastructure",
    "energy",
    "region",
    "unknown",
]


RelationType = Literal[
    "requires",
    "supplied_by",
    "depends_on",
    "manufactured_by",
    "hosted_on",
    "powered_by",
    "enabled_by",
    "hypothesized",
]


EdgeValueMeaning = Literal[
    "importance",
    "confidence_weight",
    "estimated_spend",
    "capacity_dependency",
]


SupplyChainStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "needs_review",
]


SourceType = Literal[
    "web",
    "filing",
    "transcript",
    "company",
    "manual",
    "fixture",
]


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class SupplyChainExploreRequest(BaseModel):
    """Top-level request for the supply chain explorer.

    Validation rules:

    - ``product_name`` is required and non-empty.
    - At least one of ``company_name`` or ``ticker`` must be
      present. Recursive expansion is a separate request model
      (``SupplyChainExpandRequest``) so the constraint is
      enforceable here.
    """

    model_config = ConfigDict(extra="forbid")

    company_name: str | None = None
    ticker: str | None = None
    product_name: str = Field(min_length=1)
    max_depth: int = Field(default=3, ge=1, le=5)
    max_suppliers_per_node: int = Field(default=5, ge=1, le=10)
    focus_regions: list[str] = Field(default_factory=list)
    include_private_companies: bool = True
    demo_mode: bool = False
    cached_mode: bool = False

    @model_validator(mode="after")
    def _require_company(self) -> SupplyChainExploreRequest:
        if not (self.company_name or self.ticker):
            raise ValueError(
                "company_name or ticker is required for SupplyChainExploreRequest"
            )
        if self.product_name.strip() == "":
            raise ValueError("product_name must not be blank")
        return self


class SupplyChainExpandRequest(BaseModel):
    """Recursive expansion request.

    The child workflow uses ``node_id`` as the new seed product;
    ``seed_companies`` narrows the supplier search. ``max_depth`` is
    bounded tighter (1-4) because expansions are always one level
    deeper than the parent.
    """

    model_config = ConfigDict(extra="forbid")

    parent_run_id: str
    node_id: str
    product_name: str | None = None
    seed_companies: list[str] = Field(default_factory=list)
    max_depth: int = Field(default=2, ge=1, le=4)
    max_suppliers_per_node: int = Field(default=5, ge=1, le=10)
    demo_mode: bool = False
    cached_mode: bool = False

    @field_validator("node_id")
    @classmethod
    def _node_id_nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("node_id must not be blank")
        return value


# ---------------------------------------------------------------------------
# Graph primitives
# ---------------------------------------------------------------------------


class SupplyChainNode(BaseModel):
    """A single node in the supply chain graph.

    The spec requires stable ``node_id`` values: the demo fixture
    uses colon-separated slugs (``company:openai``,
    ``component:gpu-accelerator``) so they sort and display well.
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: NodeType
    label: str
    normalized_name: str
    ticker: str | None = None
    depth: int = Field(ge=0, le=10)
    parent_node_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupplyChainEdge(BaseModel):
    """A single directed edge between two nodes.

    Confirmed edges must have at least one ``evidence_id``.
    Hypothesised edges may omit evidence but must record the
    reason in ``metadata["reason"]`` so the evaluator can downgrade
    them.
    """

    model_config = ConfigDict(extra="forbid")

    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: RelationType
    value: float = Field(ge=0.0)
    value_meaning: EdgeValueMeaning = "importance"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _confirmed_must_have_evidence(self) -> SupplyChainEdge:
        if self.relation_type != "hypothesized" and not self.evidence_ids:
            raise ValueError(
                f"edge {self.edge_id} is confirmed but has no evidence_ids"
            )
        if self.source_node_id == self.target_node_id:
            raise ValueError(
                f"edge {self.edge_id} is a self-loop on {self.source_node_id}"
            )
        return self


class NormalizedSupplyChainEvidence(BaseModel):
    """A single evidence row backing a node or an edge."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_type: SourceType
    source_name: str | None = None
    url: str | None = None
    title: str | None = None
    quote: str
    summary: str
    retrieved_at: datetime
    published_at: datetime | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Sankey payload
# ---------------------------------------------------------------------------


class SankeyPayload(BaseModel):
    """The frontend's Sankey payload.

    Validation enforces:

    - every link references nodes that exist;
    - no self-loop;
    - no cycle (v18: confirmed cycles fail, hypothesised cycles are
      dropped with a warning).
    """

    model_config = ConfigDict(extra="forbid")

    nodes: list[SupplyChainNode]
    links: list[SupplyChainEdge]
    evidence: list[NormalizedSupplyChainEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_graph(self) -> SankeyPayload:
        node_ids = {n.node_id for n in self.nodes}
        for link in self.links:
            if link.source_node_id not in node_ids:
                raise ValueError(
                    f"link {link.edge_id} source {link.source_node_id} not in nodes"
                )
            if link.target_node_id not in node_ids:
                raise ValueError(
                    f"link {link.edge_id} target {link.target_node_id} not in nodes"
                )
            if link.source_node_id == link.target_node_id:
                raise ValueError(
                    f"link {link.edge_id} is a self-loop"
                )
        # cycle detection (confirmed edges only)
        adjacency: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for link in self.links:
            if link.relation_type != "hypothesized":
                adjacency[link.source_node_id].append(link.target_node_id)
        if _has_cycle(adjacency):
            raise ValueError("SankeyPayload contains a confirmed cycle")
        return self


def _has_cycle(adjacency: dict[str, list[str]]) -> bool:
    """Return True if the directed graph has any cycle."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(adjacency, WHITE)

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for nxt in adjacency[node]:
            if color[nxt] == GRAY:
                return True
            if color[nxt] == WHITE and dfs(nxt):
                return True
        color[node] = BLACK
        return False

    return any(color[n] == WHITE and dfs(n) for n in adjacency)


# ---------------------------------------------------------------------------
# Trace + evaluation
# ---------------------------------------------------------------------------


class SupplyChainTraceEvent(BaseModel):
    """A single trace row emitted by a supply chain step."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: f"sc-tr-{uuid.uuid4().hex[:8]}")
    step_name: str
    status: Literal["completed", "running", "failed", "skipped"]
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    fallback_used: str | None = None


class SupplyChainEvaluation(BaseModel):
    """Guardrail summary for the supply chain workflow."""

    model_config = ConfigDict(extra="forbid")

    final_status: SupplyChainStatus = "completed"
    node_count: int = Field(ge=0)
    link_count: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    confirmed_edge_count: int = Field(ge=0)
    hypothesised_edge_count: int = Field(ge=0)
    unsupported_edges: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = False


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class SupplyChainExploreState(BaseModel):
    """Workflow state for the supply chain explorer.

    The shape mirrors ``FinRiskWorkflowState`` so the v18 API and
    the v17 run store can share validation helpers.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    request: SupplyChainExploreRequest
    status: SupplyChainStatus = "queued"
    nodes: list[SupplyChainNode] = Field(default_factory=list)
    links: list[SupplyChainEdge] = Field(default_factory=list)
    evidence: list[NormalizedSupplyChainEvidence] = Field(default_factory=list)
    sankey: SankeyPayload | None = None
    evaluation: SupplyChainEvaluation | None = None
    trace: list[SupplyChainTraceEvent] = Field(default_factory=list)
    parent_run_id: str | None = None
    expanded_from_node_id: str | None = None
    fallback_events: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


__all__ = [
    "EdgeValueMeaning",
    "NodeType",
    "NormalizedSupplyChainEvidence",
    "RelationType",
    "SankeyEvaluation",
    "SankeyPayload",
    "SourceType",
    "SupplyChainEdge",
    "SupplyChainEvaluation",
    "SupplyChainExpandRequest",
    "SupplyChainExploreRequest",
    "SupplyChainExploreState",
    "SupplyChainNode",
    "SupplyChainStatus",
    "SupplyChainTraceEvent",
]


# ``SankeyEvaluation`` is a deprecated alias kept for backward
# compatibility with the v18 spec draft; new code should use
# ``SupplyChainEvaluation``.
SankeyEvaluation = SupplyChainEvaluation
