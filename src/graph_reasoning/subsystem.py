"""Top-level orchestrator for the v16 graph reasoning pipeline.

The subsystem is a thin wrapper over the six stages defined in
``context_builder``, ``path_retriever``, ``path_scorer``,
``evidence_binder``, ``path_interpreter``, and
``insight_validator``. The orchestrator never raises; any
unexpected failure produces an empty :class:`EvidenceGraphPayload`
so the rest of the workflow can still finish.
"""

from __future__ import annotations

import logging

from src.evaluation.models import GuardrailFinding
from src.graph_reasoning.backends import (
    FixtureGraphBackend,
    GraphPathBackend,
)
from src.graph_reasoning.context_builder import build_graph_context
from src.graph_reasoning.insight_validator import validate_all
from src.graph_reasoning.models import (
    CandidateGraphPath,
    EvidenceGraphPayload,
    GraphInsightV16,
)
from src.graph_reasoning.path_interpreter import interpret_paths
from src.graph_reasoning.path_scorer import rank_paths
from src.schemas.finrisk import FinRiskWorkflowState

logger = logging.getLogger(__name__)


class GraphReasoningSubsystem:
    """Run the six-stage pipeline against a workflow state."""

    def __init__(
        self,
        *,
        top_k_paths: int = 3,
        top_k_insights: int = 1,
        backend: GraphPathBackend | None = None,
    ) -> None:
        self.top_k_paths = top_k_paths
        self.top_k_insights = top_k_insights
        self.backend = backend or FixtureGraphBackend()

    def run(
        self,
        state: FinRiskWorkflowState,
        *,
        custom_paths: list[CandidateGraphPath] | None = None,
    ) -> EvidenceGraphPayload:
        context = build_graph_context(state)
        try:
            if custom_paths is not None:
                candidates = custom_paths
            else:
                candidates = self.backend.retrieve(context)
        except Exception as exc:
            logger.exception("path retriever failed")
            return EvidenceGraphPayload(
                guardrail_findings=[
                    GuardrailFinding(
                        step_name="graph_reasoner",
                        check_name="graph_path",
                        status="needs_review",
                        severity="warning",
                        message=f"path retriever failed: {exc}",
                        affected_object_type="graph_path",
                    ).model_dump()
                ]
            )
        ranked = rank_paths(candidates, context, state)
        top_paths = ranked[: self.top_k_paths]
        insights: list[GraphInsightV16] = interpret_paths(
            top_paths, state, top_k=self.top_k_insights
        )
        findings = validate_all(insights, state, top_paths)
        return EvidenceGraphPayload(
            nodes=[n for p in top_paths for n in p.nodes],
            edges=[e for p in top_paths for e in p.edges],
            paths=top_paths,
            insights=insights,
            guardrail_findings=[f.model_dump() for f in findings],
        )


__all__ = ["GraphReasoningSubsystem"]
