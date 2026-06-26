"""Pydantic schemas for the FinRisk Agent Studio workflow.

These schemas are the canonical contract between the workflow orchestrator,
the API, the frontend, and any downstream consumers. All steps must read
and write only ``FinRiskWorkflowState`` (and its nested types), never
loose ``dict`` objects.

Conventions:
- ``datetime`` fields are timezone-aware (``datetime.now(timezone.utc)``).
- ``extra="forbid"`` everywhere so typos surface at validation time.
- All identifiers are stable strings, not ints, so JSON round-trips
  do not depend on ordering.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas.llm_config import LLMRunConfig

RiskType = Literal[
    "macro",
    "policy",
    "climate",
    "supply_chain",
    "competition",
    "regulatory",
    "technology",
    "geopolitical",
    "financial",
    "operational",
]

MarketSourceType = Literal[
    "news",
    "financial",
    "regulatory",
    "company",
    "filing",
    "transcript",
    "other",
]

NormalizedSourceType = Literal[
    "filing",
    "web",
    "transcript",
    "graph",
    "fixture",
]

WorkflowStatus = Literal[
    "created",
    "running",
    "completed",
    "failed",
    "needs_review",
]

TraceStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
]

EvaluationStatus = Literal["pass", "needs_review", "fail"]


class FinRiskRequest(BaseModel):
    """The user-facing request that kicks off the workflow."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    company_name: str | None = None
    analysis_goal: str
    time_horizon: str = "6-12 months"
    year: int | None = None
    sources: list[Literal["filing", "web", "transcript", "graph"]] = Field(
        default_factory=lambda: ["filing", "web", "graph"]
    )
    max_browser_steps: int = Field(default=5, ge=0, le=20)
    demo_mode: bool = False
    cached_mode: bool = False
    llm_config: LLMRunConfig = Field(default_factory=LLMRunConfig)

    @field_validator("ticker")
    @classmethod
    def _upper_ticker(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            msg = "ticker must not be empty"
            raise ValueError(msg)
        return cleaned

    @field_validator("analysis_goal")
    @classmethod
    def _non_empty_goal(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "analysis_goal must not be empty"
            raise ValueError(msg)
        return cleaned

    @field_validator("sources")
    @classmethod
    def _non_empty_sources(cls, value: list[str]) -> list[str]:
        if not value:
            msg = "sources must contain at least one entry"
            raise ValueError(msg)
        # Dedupe while preserving order.
        seen: set[str] = set()
        out: list[str] = []
        for src in value:
            if src in seen:
                continue
            seen.add(src)
            out.append(src)
        return out


class CompanyProfile(BaseModel):
    """The output of step 1: who is the user actually analyzing?"""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    ticker: str
    cik: str | None = None
    filing_type: str | None = "10-K"
    analysis_year: int | None = None
    source: Literal[
        "sec_company_tickers", "cache", "fixture", "manual", "unknown"
    ] = "unknown"
    resolved_at: datetime

    @field_validator("ticker")
    @classmethod
    def _upper_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("cik")
    @classmethod
    def _pad_cik(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return cleaned.zfill(10)


class ExtractedRisk(BaseModel):
    """A typed risk row produced by the filing risk extractor."""

    model_config = ConfigDict(extra="forbid")

    risk_id: str
    risk_type: RiskType
    risk_factor: str
    severity: int = Field(ge=1, le=5)
    evidence_quote: str
    source: str
    filing_section: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("evidence_quote", "risk_factor", "source")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "field must not be empty"
            raise ValueError(msg)
        return cleaned


class MarketEvidence(BaseModel):
    """Web / search / browser evidence attached to a risk."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    risk_id: str | None = None
    source_url: str
    source_title: str | None = None
    source_type: MarketSourceType
    claim: str
    evidence_summary: str
    supports_risk: bool | None = None
    contradicts_risk: bool | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime

    @field_validator("source_url")
    @classmethod
    def _valid_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
            msg = f"source_url must be http(s); got {value!r}"
            raise ValueError(msg)
        return cleaned

    @field_validator("claim", "evidence_summary")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "field must not be empty"
            raise ValueError(msg)
        return cleaned


class NormalizedEvidence(BaseModel):
    """Filing / web / transcript evidence in a unified shape."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_type: NormalizedSourceType
    source_name: str
    source_url: str | None = None
    quote: str | None = None
    summary: str
    related_risk_ids: list[str] = Field(default_factory=list)
    credibility_score: float = Field(ge=0.0, le=1.0)
    collected_at: datetime
    published_at: datetime | None = None

    @field_validator("source_url")
    @classmethod
    def _valid_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
            msg = f"source_url must be http(s); got {value!r}"
            raise ValueError(msg)
        return cleaned

    @field_validator("summary", "source_name")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "field must not be empty"
            raise ValueError(msg)
        return cleaned


class RiskScore(BaseModel):
    """Deterministic score for one risk."""

    model_config = ConfigDict(extra="forbid")

    risk_id: str
    base_severity: int = Field(ge=1, le=5)
    recent_signal_strength: float = Field(ge=0.0, le=1.0)
    evidence_quality: float = Field(ge=0.0, le=1.0)
    source_diversity: float = Field(ge=0.0, le=1.0)
    novelty_score: float = Field(ge=0.0, le=1.0)
    graph_centrality: float | None = Field(default=None, ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
    score_reasoning: str

    @field_validator("score_reasoning")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "score_reasoning must not be empty"
            raise ValueError(msg)
        return cleaned


class GraphInsight(BaseModel):
    """A graph-derived second-order effect or supply-chain path."""

    model_config = ConfigDict(extra="forbid")

    insight_id: str
    source_company: str
    affected_entity: str
    risk_path: list[str] = Field(default_factory=list)
    investment_theme: str | None = None
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("risk_path")
    @classmethod
    def _at_least_two(cls, value: list[str]) -> list[str]:
        if len(value) < 2:
            msg = "risk_path must contain at least 2 nodes"
            raise ValueError(msg)
        return value


class RiskReport(BaseModel):
    """Final research brief."""

    model_config = ConfigDict(extra="forbid")

    title: str
    executive_summary: str
    top_risks: list[ExtractedRisk] = Field(default_factory=list)
    risk_scores: list[RiskScore] = Field(default_factory=list)
    evidence_table: list[NormalizedEvidence] = Field(default_factory=list)
    graph_insights: list[GraphInsight] = Field(default_factory=list)
    evidence_vs_inference: str
    limitations: str
    recommended_next_questions: list[str] = Field(default_factory=list)
    markdown: str

    @field_validator("limitations", "evidence_vs_inference", "markdown")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            msg = "field must not be empty"
            raise ValueError(msg)
        return cleaned


class WorkflowTraceEvent(BaseModel):
    """One row per workflow step for the timeline UI."""

    model_config = ConfigDict(extra="forbid")

    step_name: str
    status: TraceStatus
    started_at: datetime
    completed_at: datetime | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    error: str | None = None
    retry_count: int = 0


# ---------------------------------------------------------------------------
# Per-step / per-chunk observability (added 2026-06-25).
#
# Every LLM call the workflow makes writes one ``LLMCall`` row; every
# chunk that flows through ``filing_risk_extractor`` writes one
# ``ChunkValidation`` row; the section parser writes one
# ``SectionLocation`` row per matched section; the lifecycle
# classifier writes one ``RiskLifecycleAnnotation`` per risk.
#
# The frontend's ``StepOutputInspector`` component renders these as
# JSON-formatted lists with one tab per category so an engineer
# debugging a real run can see exactly what the LLM saw, what it
# returned, and whether the Pydantic validation succeeded.
# ---------------------------------------------------------------------------

RiskLifecycle = Literal["current", "emerging", "receding", "unknown"]


class SectionLocation(BaseModel):
    """Where a canonical section was located in the source filing.

    ``char_start`` and ``char_end`` are offsets into ``full_text`` after
    HTML stripping + entity unescape. ``matched_against_real_section``
    is True when the parser picked a substantive match (the longest
    candidate >= the min-substantive threshold) rather than the
    Forward-Looking Statements disclaimer match.
    """

    model_config = ConfigDict(extra="forbid")

    section_name: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    char_count: int = Field(ge=0)
    matched_against_real_section: bool = True
    matched_section_reason: str = ""
    is_disclaimer_text: bool = False
    filing_accession: str | None = None
    filing_form: str | None = None


class ChunkValidation(BaseModel):
    """Result of Pydantic-validating one chunk's LLM output.

    ``ok`` is True when every item the LLM returned parsed cleanly
    against the target schema (``ExtractedRisk``). ``dropped_count``
    is the number of items that failed validation and were excluded
    from the final risk list (they still appear in ``llm_log`` for
    audit).
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    pydantic_model: str = "ExtractedRisk"
    ok: bool = True
    errors: list[str] = Field(default_factory=list)
    validated_count: int = 0
    dropped_count: int = 0
    fallback_used: Literal["llm", "keyword", "fixture", "demo"] | None = None
    section_name: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    validated_at: datetime


class LLMCall(BaseModel):
    """One chat-completion call made by any step.

    Captures the full chat history, the structured response (when
    parsable), token usage, latency, and any error. The frontend
    inspector renders ``prompt_text`` + ``response_text`` as
    collapsible JSON blocks.
    """

    model_config = ConfigDict(extra="forbid")

    call_id: str
    step_name: str
    chunk_id: str | None = None
    provider: str
    model: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    prompt_text: str = ""
    response_text: str = ""
    response_structured: dict[str, Any] | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int = Field(ge=0)
    error: str | None = None
    started_at: datetime
    completed_at: datetime


class RiskLifecycleAnnotation(BaseModel):
    """Lifecycle classification for one ``ExtractedRisk``.

    ``lifecycle`` is one of ``current`` / ``emerging`` / ``receding`` /
    ``unknown``. ``basis`` lists the evidence_ids that drove the
    classification; ``reasoning`` is the human-readable explanation.
    """

    model_config = ConfigDict(extra="forbid")

    risk_id: str
    lifecycle: RiskLifecycle = "unknown"
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    basis: list[str] = Field(default_factory=list)
    classified_at: datetime


class WorkflowEvaluation(BaseModel):
    """Guardrail verdict for a completed workflow."""

    model_config = ConfigDict(extra="forbid")

    schema_valid: bool
    has_evidence_for_each_risk: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    financial_advice_risk: bool
    source_diversity_score: float = Field(ge=0.0, le=1.0)
    hallucination_risk_score: float = Field(ge=0.0, le=1.0)
    final_status: EvaluationStatus


class FinRiskWorkflowState(BaseModel):
    """The single mutable object that flows between workflow steps."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    request: FinRiskRequest
    company: CompanyProfile | None = None
    filing_risks: list[ExtractedRisk] = Field(default_factory=list)
    market_evidence: list[MarketEvidence] = Field(default_factory=list)
    normalized_evidence: list[NormalizedEvidence] = Field(default_factory=list)
    risk_scores: list[RiskScore] = Field(default_factory=list)
    graph_insights: list[GraphInsight] = Field(default_factory=list)
    report: RiskReport | None = None
    evaluation: WorkflowEvaluation | None = None
    trace: list[WorkflowTraceEvent] = Field(default_factory=list)
    status: WorkflowStatus = "created"
    # --- v16 quality layer / graph reasoning additions ---
    # The fields below are typed as Any to avoid an import cycle with
    # :mod:`src.evaluation.models`; the v16 code populates them with
    # Claim / StepEvaluation / WorkflowEvaluationV16 / FallbackEvent
    # / GuardrailFinding / CandidateGraphPath instances whose schema
    # is enforced at the assignment site via ``model_validate``.
    # --- v16 quality layer / graph reasoning additions ---
    # v17: the v16 state fields keep the v15 ``list`` / ``Any`` type
    # annotations so the state model does not have to import every
    # v16 sub-module. The runtime contract is enforced by
    # ``model_validate`` at the assignment site (see
    # ``src.workflows.quality_gate`` and the graph reasoner / report
    # generator) and by the v17 tests under
    # ``tests/schemas/test_finrisk_v16_state.py``.
    #
    # The expected runtime types are documented in
    # ``docs/specs/v17-code-audit-remediation/03-v16-state-report-and-score-path.md``.
    claims: list = Field(default_factory=list)  # v16 Claim
    graph_context: Any | None = None
    graph_paths: list = Field(default_factory=list)  # v16 CandidateGraphPath
    graph_payload: Any | None = None  # v16 EvidenceGraphPayload
    graph_insights_v16: list = Field(default_factory=list)  # v16 GraphInsightV16
    risk_scores_v16: list = Field(default_factory=list)  # v16 RiskScoreV16
    report_v16: Any | None = None  # v16 RiskReportV16
    evaluations: list = Field(default_factory=list)  # v16 StepEvaluation
    workflow_evaluation: Any | None = None  # v16 WorkflowEvaluationV16
    guardrail_findings: list = Field(default_factory=list)  # v16 GuardrailFinding
    fallback_events: list = Field(default_factory=list)  # v16 FallbackEvent
    # --- v17 per-step observability (LLMCall / ChunkValidation /
    # SectionLocation / RiskLifecycleAnnotation). The StepOutputInspector
    # on the frontend reads these via /workflows/{id}/llm_log,
    # /chunks, /sections, /lifecycles respectively. ---
    llm_log: list[LLMCall] = Field(default_factory=list)
    chunk_validations: list[ChunkValidation] = Field(default_factory=list)
    section_locations: list[SectionLocation] = Field(default_factory=list)
    risk_lifecycles: list[RiskLifecycleAnnotation] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(tz=UTC)


__all__ = [
    "CompanyProfile",
    "EvaluationStatus",
    "ExtractedRisk",
    "FinRiskRequest",
    "FinRiskWorkflowState",
    "GraphInsight",
    "MarketEvidence",
    "MarketSourceType",
    "NormalizedEvidence",
    "NormalizedSourceType",
    "RiskReport",
    "RiskScore",
    "RiskType",
    "TraceStatus",
    "WorkflowEvaluation",
    "WorkflowStatus",
    "WorkflowTraceEvent",
    "utcnow",
]
