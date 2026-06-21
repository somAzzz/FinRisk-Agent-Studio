"""Tests for the AgentState / ToolCall models."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.agents.state import AgentState, ToolCall


def _evidence() -> dict[str, object]:
    return {
        "evidence_id": "ev1",
        "source_type": "sec_filing",
        "source_id": "0001",
        "quote": "Some quote",
        "retrieved_at": datetime(2026, 6, 20, tzinfo=timezone.utc),
        "confidence": 0.9,
    }


def test_agent_state_defaults() -> None:
    state = AgentState(goal="understand AAPL")
    assert state.ticker is None
    assert state.company_name is None
    assert state.claims == []
    assert state.evidence == []
    assert state.entities == []
    assert state.relations == []
    assert state.tool_history == []
    assert state.notes == []
    assert state.max_steps == 10
    assert state.current_step == 0


def test_agent_state_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        AgentState(goal="x", unknown_field="nope")  # type: ignore[call-arg]


def test_agent_state_json_round_trip() -> None:
    state = AgentState(
        goal="understand AAPL",
        ticker="AAPL",
        evidence=[_evidence()],  # type: ignore[list-item]
        notes=["a note"],
    )
    payload = state.model_dump_json()
    decoded = AgentState.model_validate_json(payload)
    assert decoded == state
    # Sanity: the JSON really is JSON.
    json.loads(payload)


def test_tool_call_fields() -> None:
    now = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
    call = ToolCall(
        tool_name="fetch_filing",
        arguments={"ticker": "AAPL"},
        result_summary="ok",
        success=True,
        created_at=now,
    )
    assert call.tool_name == "fetch_filing"
    assert call.arguments == {"ticker": "AAPL"}
    assert call.result_summary == "ok"
    assert call.success is True
    assert call.created_at == now


def test_tool_call_extra_forbid() -> None:
    now = datetime(2026, 6, 20, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        ToolCall(
            tool_name="x",
            arguments={},
            created_at=now,
            bogus="nope",  # type: ignore[call-arg]
        )
