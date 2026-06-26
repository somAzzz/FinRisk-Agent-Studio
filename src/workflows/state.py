"""Workflow state re-exports for convenient importing.

The canonical types live in :mod:`src.schemas.finrisk`. This module
exists so workflow step implementations can ``from src.workflows.state
import FinRiskWorkflowState`` without depending on the schemas
subpackage directly.
"""

from __future__ import annotations

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

# ---------------------------------------------------------------------------
# v16 forward-reference resolution
# ---------------------------------------------------------------------------
# ``FinRiskWorkflowState`` (in ``src.schemas.finrisk``) declares its
# v16 fields with string annotations to break an import cycle with
# :mod:`src.schemas.finrisk_v16`. Now that the import graph is fully
# resolved (this module is the deepest point on the cycle), force
# Pydantic to rebuild the model's schema so the string annotations
# resolve to the v16 classes.
from src.schemas import finrisk_v16 as _v16

# The annotations in ``finrisk.FinRiskWorkflowState`` are evaluated
# against the *importing* module's globals (this file), so we bind
# the v16 names here for Pydantic to find.
_typing = __import__("typing")
_typing.cast("_typing.Any", globals()).update(
    {name: getattr(_v16, name) for name in _v16.__all__}
)
FinRiskWorkflowState.model_rebuild()
