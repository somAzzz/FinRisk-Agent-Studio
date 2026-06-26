"""Shared schemas for FinText-LLM.

Centralizes the data contracts used across data ingestion, agents,
graph storage, and analysis modules.
"""

from src.schemas.claims import Claim, ClaimType
from src.schemas.entities import Entity, EntityType
from src.schemas.evidence import Evidence, SourceType
from src.schemas.filings import FilingMetadata, FilingRecord
from src.schemas.ids import stable_id
from src.schemas.relations import Relation, RelationType
from src.schemas.transcripts import Transcript, TranscriptMeta, TranscriptTurn

__all__ = [
    "Claim",
    "ClaimType",
    "Entity",
    "EntityType",
    "Evidence",
    "FilingMetadata",
    "FilingRecord",
    "Relation",
    "RelationType",
    "SourceType",
    "Transcript",
    "TranscriptMeta",
    "TranscriptTurn",
    "stable_id",
]

from src.schemas.finrisk import (
    CompanyProfile,
    EvaluationStatus,
    ExtractedRisk,
    FinRiskRequest,
    FinRiskWorkflowState,
    GraphInsight,
    MarketEvidence,
    MarketSourceType,
    NormalizedEvidence,
    NormalizedSourceType,
    RiskReport,
    RiskScore,
    RiskType,
    TraceStatus,
    WorkflowEvaluation,
    WorkflowStatus,
    WorkflowTraceEvent,
    utcnow,
)

__all__ += [
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

# Note: the v16 forward-reference resolution happens inside
# :mod:`src.schemas.finrisk` (see the post-class import block there).
# We deliberately do *not* call ``model_rebuild`` here because
# ``FinRiskWorkflowState.model_rebuild`` is invoked by the
# ``finrisk`` module itself once the v16 types are bound.
