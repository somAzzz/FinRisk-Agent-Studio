"""Pydantic models for the v19 evidence-first context layer."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MemoryType = Literal[
    "evidence",
    "graph_edge",
    "claim",
    "episode",
    "domain_prior",
    "policy",
]

MemorySourceType = Literal[
    "filing",
    "company",
    "regulatory",
    "news",
    "transcript",
    "web",
    "graph",
    "domain_prior",
    "human_feedback",
    "fixture",
    "manual",
]

ClaimType = Literal["evidence", "inference", "hypothesis", "policy"]

MemoryStatus = Literal[
    "candidate",
    "validated",
    "active",
    "used",
    "stale",
    "superseded",
    "rejected",
    "deprecated",
]

ContextEvaluationStatus = Literal["pass", "warning", "fail"]


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(tz=UTC)


def stable_memory_hash(
    *,
    text: str,
    source_type: str,
    source_url: str | None = None,
    memory_type: str | None = None,
) -> str:
    """Build a deterministic hash for memory dedupe."""
    payload = {
        "memory_type": memory_type or "",
        "source_type": source_type,
        "source_url": source_url or "",
        "text": " ".join(text.lower().split()),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class MemoryItem(BaseModel):
    """A long-lived memory record used by context selection."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(default_factory=lambda: f"mem-{uuid.uuid4().hex[:12]}")
    memory_type: MemoryType
    text: str
    summary: str | None = None
    source_type: MemorySourceType
    source_url: str | None = None
    source_title: str | None = None
    entities: list[str] = Field(default_factory=list)
    tickers: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=utcnow)
    first_seen_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow)
    last_used_at: datetime | None = None
    credibility_score: float = Field(ge=0.0, le=1.0)
    freshness_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    claim_type: ClaimType
    status: MemoryStatus = "candidate"
    hash: str = ""
    embedding_id: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def _text_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("MemoryItem.text must be non-empty")
        return value.strip()

    @model_validator(mode="after")
    def _derive_hash(self) -> MemoryItem:
        if not self.hash:
            self.hash = stable_memory_hash(
                text=self.text,
                source_type=self.source_type,
                source_url=self.source_url,
                memory_type=self.memory_type,
            )
        return self


class ContextCandidate(BaseModel):
    """A ranked candidate considered for a ContextPack."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str
    reason_selected: str
    semantic_relevance: float = Field(ge=0.0, le=1.0)
    source_credibility: float = Field(ge=0.0, le=1.0)
    freshness: float = Field(ge=0.0, le=1.0)
    graph_proximity: float = Field(ge=0.0, le=1.0)
    diversity_contribution: float = Field(ge=0.0, le=1.0)
    prior_success_score: float = Field(ge=0.0, le=1.0)
    primary_source_bonus: float = Field(ge=0.0, le=1.0)
    contradiction_bonus: float = Field(ge=0.0, le=1.0)
    duplicate_penalty: float = Field(ge=0.0, le=1.0)
    staleness_penalty: float = Field(ge=0.0, le=1.0)
    rejected_memory_penalty: float = Field(ge=0.0, le=1.0)
    final_context_score: float


class ContextEvidenceReference(BaseModel):
    """Trimmed evidence reference included in a ContextPack."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str
    quote: str
    summary: str | None = None
    source_type: MemorySourceType
    source_url: str | None = None
    source_title: str | None = None
    claim_type: ClaimType
    status: MemoryStatus
    context_score: float


class GraphPathReference(BaseModel):
    """Minimal graph path reference for graph-aware context packs."""

    model_config = ConfigDict(extra="forbid")

    path_id: str
    summary: str
    memory_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ContextPack(BaseModel):
    """The bounded context passed to a workflow step."""

    model_config = ConfigDict(extra="forbid")

    context_pack_id: str = Field(default_factory=lambda: f"ctx-{uuid.uuid4().hex[:12]}")
    run_id: str
    step_name: str
    task: str
    objective: str
    constraints: list[str] = Field(default_factory=list)
    selected_evidence: list[ContextEvidenceReference] = Field(default_factory=list)
    selected_graph_paths: list[GraphPathReference] = Field(default_factory=list)
    prior_findings: list[str] = Field(default_factory=list)
    negative_memory: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    token_budget: int = Field(default=4000, ge=1)
    estimated_tokens: int = Field(default=0, ge=0)
    freshness_window_days: int | None = Field(default=None, ge=1)
    selection_policy_version: str = "context-selection-v1"
    selected_memory_ids: list[str] = Field(default_factory=list)
    rejected_memory_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ContextPackEvaluation(BaseModel):
    """Guardrail evaluation for a ContextPack."""

    model_config = ConfigDict(extra="forbid")

    context_pack_id: str
    status: ContextEvaluationStatus
    token_budget_used: float = Field(ge=0.0)
    source_diversity_score: float = Field(ge=0.0, le=1.0)
    stale_memory_count: int = Field(ge=0)
    rejected_memory_count: int = Field(ge=0)
    hypothesis_count: int = Field(ge=0)
    missing_contradictions: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class WorkflowEpisode(BaseModel):
    """A compact memory record for a completed workflow run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_type: Literal["finrisk", "supply_chain"]
    input_fingerprint: str
    successful_queries: list[str] = Field(default_factory=list)
    failed_queries: list[str] = Field(default_factory=list)
    accepted_claims: list[str] = Field(default_factory=list)
    rejected_claims: list[str] = Field(default_factory=list)
    rejected_graph_edges: list[str] = Field(default_factory=list)
    guardrail_failures: list[str] = Field(default_factory=list)
    evaluation_status: str
    lessons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class MemoryWriteDecision(BaseModel):
    """Decision emitted before writing a memory item."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str
    allowed: bool
    target_status: MemoryStatus | None = None
    reasons: list[str] = Field(default_factory=list)


class MemoryReadDecision(BaseModel):
    """Decision emitted when selecting or rejecting memory for context."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str
    selected: bool
    reason: str
    context_score: float


__all__ = [
    "ClaimType",
    "ContextCandidate",
    "ContextEvaluationStatus",
    "ContextEvidenceReference",
    "ContextPack",
    "ContextPackEvaluation",
    "GraphPathReference",
    "MemoryItem",
    "MemoryReadDecision",
    "MemorySourceType",
    "MemoryStatus",
    "MemoryType",
    "MemoryWriteDecision",
    "WorkflowEpisode",
    "stable_memory_hash",
    "utcnow",
]
