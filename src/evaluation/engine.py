"""Guardrail engine: orchestrates the per-step validators.

The engine has three responsibilities:

1. Run pre-step validation on a state.
2. Run post-step validation on the step's output and update state.
3. Aggregate every step's :class:`StepEvaluation` into a
   :class:`WorkflowEvaluationV16` summary.

The engine never raises; any validator exception is converted to a
BLOCKER finding so the workflow trace still shows what went wrong.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.evaluation.models import (
    FallbackEvent,
    GuardrailFinding,
    GuardrailSeverity,
    GuardrailStatus,
    StepEvaluation,
    WorkflowEvaluationV16,
    aggregate_status,
    build_workflow_evaluation,
)
from src.evaluation.metrics import (
    hallucination_risk_score,
    source_diversity_score,
)
from src.evaluation.validators.base import Validator
from src.schemas.finrisk import FinRiskWorkflowState
from src.workflows.state import utcnow

logger = logging.getLogger(__name__)


_DEFAULT_VALIDATORS: tuple[Validator, ...] = ()


def _safe_validate(
    validators: list[Validator],
    step_name: str,
    output: Any,
    state: FinRiskWorkflowState,
) -> list[GuardrailFinding]:
    """Run every validator and swallow any internal exception."""
    findings: list[GuardrailFinding] = []
    for v in validators:
        try:
            findings.extend(v.validate(step_name, output, state))
        except Exception as exc:  # noqa: BLE001
            logger.exception("validator %s raised", getattr(v, "name", v))
            findings.append(
                GuardrailFinding(
                    step_name=step_name,
                    check_name=getattr(v, "name", "validator"),
                    status=GuardrailStatus.FAIL,
                    severity=GuardrailSeverity.BLOCKER,
                    message=f"validator exception: {type(exc).__name__}: {exc}",
                    affected_object_type="workflow",
                )
            )
    return findings


def _status_for(findings: list[GuardrailFinding]) -> GuardrailStatus:
    if any(f.severity == GuardrailSeverity.BLOCKER for f in findings):
        return GuardrailStatus.FAIL
    if any(f.severity == GuardrailSeverity.WARNING for f in findings):
        return GuardrailStatus.NEEDS_REVIEW
    return GuardrailStatus.PASS


class GuardrailEngine:
    """Stateless aggregator of validators and step evaluations."""

    def __init__(self, validators: list[Validator] | None = None) -> None:
        self._validators: list[Validator] = list(validators or [])

    @property
    def validators(self) -> list[Validator]:
        return list(self._validators)

    def add_validator(self, validator: Validator) -> None:
        self._validators.append(validator)

    def validate_pre_step(
        self,
        step_name: str,
        state: FinRiskWorkflowState,
    ) -> StepEvaluation:
        """Run validators on the state before the step executes.

        The pre-step check exists so a bad state (e.g. an empty
        company profile) is caught before the step tries to read
        from it. Validators receive ``output=None``.
        """
        started = time.perf_counter()
        findings = _safe_validate(self._validators, step_name, None, state)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return StepEvaluation(
            step_name=step_name,
            status=_status_for(findings),
            findings=findings,
            latency_ms=latency_ms,
        )

    def validate_post_step(
        self,
        step_name: str,
        output: Any,
        state: FinRiskWorkflowState,
        *,
        fallback_used: str | None = None,
    ) -> StepEvaluation:
        """Run validators on the step's output and update the state.

        The :class:`StepEvaluation` is also appended to
        ``state.evaluations`` so the workflow trace carries it.
        """
        started = time.perf_counter()
        findings = _safe_validate(self._validators, step_name, output, state)
        latency_ms = int((time.perf_counter() - started) * 1000)
        evaluation = StepEvaluation(
            step_name=step_name,
            status=_status_for(findings),
            findings=findings,
            latency_ms=latency_ms,
            fallback_used=fallback_used,
        )
        state.evaluations.append(evaluation)
        if fallback_used:
            state.fallback_events.append(
                FallbackEvent(
                    step_name=step_name,
                    from_mode="live",
                    to_mode=fallback_used,
                    reason="step output requested fallback",
                    occurred_at=utcnow(),
                )
            )
        # Record the evaluation back onto the state so the API can
        # surface it directly.
        for finding in findings:
            state.guardrail_findings.append(finding)
        return evaluation

    def summarize_workflow(
        self,
        state: FinRiskWorkflowState,
    ) -> WorkflowEvaluationV16:
        """Compute the v16 workflow-level evaluation from state."""
        step_evaluations = list(state.evaluations)
        overall: dict[str, float] = {
            "source_diversity": source_diversity_score(state.normalized_evidence),
            "hallucination_risk": hallucination_risk_score(state),
        }
        if state.report is not None and state.report.top_risks:
            overall["top_risk_count"] = float(len(state.report.top_risks))
        unsupported = [
            f.message
            for f in state.guardrail_findings
            if f.check_name in {"evidence", "graph_path", "claim_grounding"}
            and f.affected_object_type in {"risk", "claim", "graph_path"}
        ]
        return build_workflow_evaluation(
            run_id=state.run_id,
            step_evaluations=step_evaluations,
            overall_metrics=overall,
            unsupported_claims=unsupported,
        )


__all__ = ["GuardrailEngine"]


# Silence unused-import warnings for re-exported names that other
# modules consume from this package.
_ = aggregate_status
_ = _DEFAULT_VALIDATORS
