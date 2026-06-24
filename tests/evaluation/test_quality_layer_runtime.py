"""Tests for the v16 quality-gated step runner."""

from __future__ import annotations

import pytest

from src.evaluation.engine import GuardrailEngine
from src.evaluation.validators import SchemaValidator
from src.schemas.finrisk import FinRiskRequest, FinRiskWorkflowState
from src.workflows.quality_gate import run_step_with_quality_gate


def _state() -> FinRiskWorkflowState:
    return FinRiskWorkflowState(
        run_id="run-1",
        request=FinRiskRequest(
            ticker="AAPL", analysis_goal="test", demo_mode=True
        ),
    )


async def test_quality_gate_appends_evaluation_on_success() -> None:
    state = _state()
    engine = GuardrailEngine(validators=[SchemaValidator()])

    async def step(s: FinRiskWorkflowState) -> FinRiskWorkflowState:
        return s.model_copy(update={"status": "running"})

    new_state = await run_step_with_quality_gate(
        state, step_name="company_resolver", step_fn=step, engine=engine
    )
    assert len(new_state.evaluations) == 1
    assert new_state.evaluations[0].step_name == "company_resolver"
    assert new_state.evaluations[0].status.value == "pass"


async def test_quality_gate_marks_failure_on_exception() -> None:
    state = _state()
    engine = GuardrailEngine(validators=[SchemaValidator()])

    async def step(s: FinRiskWorkflowState) -> FinRiskWorkflowState:
        raise RuntimeError("explode")

    new_state = await run_step_with_quality_gate(
        state, step_name="company_resolver", step_fn=step, engine=engine
    )
    assert new_state.status == "failed"
    assert new_state.trace and new_state.trace[-1].error == "RuntimeError: explode"
    assert any(
        f.severity.value == "blocker" for f in new_state.guardrail_findings
    )


async def test_quality_gate_records_latency() -> None:
    state = _state()
    engine = GuardrailEngine(validators=[SchemaValidator()])

    async def step(s: FinRiskWorkflowState) -> FinRiskWorkflowState:
        return s

    new_state = await run_step_with_quality_gate(
        state, step_name="company_resolver", step_fn=step, engine=engine
    )
    last = new_state.evaluations[-1]
    assert last.latency_ms is not None and last.latency_ms >= 0
