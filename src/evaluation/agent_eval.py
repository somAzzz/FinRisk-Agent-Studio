"""Golden-case evaluation harness for V21 agent runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agents.state import AgentWorkflowKind
from src.evidence import EvidenceCandidateNormalizer
from src.schemas.tool_trace import ToolExecutionEvent
from src.workflows.state import utcnow

AgentGoldenVerdict = Literal["pass", "needs_review", "fail"]


class AgentGoldenCase(BaseModel):
    """One deterministic V21 agent golden case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    goal: str
    workflow_kind: AgentWorkflowKind = "generic_research"
    tool_events: list[dict[str, Any]]
    expected_tool_families: list[str] = Field(default_factory=list)
    expected_min_accepted_candidates: int = 0
    expected_min_rejected_candidates: int = 0
    expected_review_required: bool = False
    expected_disallowed_terms_absent: list[str] = Field(
        default_factory=lambda: ["raw cypher", "click", "type", "scroll"]
    )


class AgentGoldenResult(BaseModel):
    """Scores produced for one golden case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    tool_choice_score: float = Field(ge=0.0, le=1.0)
    evidence_discipline_score: float = Field(ge=0.0, le=1.0)
    stop_review_score: float = Field(ge=0.0, le=1.0)
    safety_boundary_pass: bool
    final_verdict: AgentGoldenVerdict
    findings: list[str] = Field(default_factory=list)


def load_agent_golden_case(path: Path | str) -> AgentGoldenCase:
    """Load one JSON golden case fixture."""
    return AgentGoldenCase.model_validate(json.loads(Path(path).read_text()))


def evaluate_agent_golden_case(case: AgentGoldenCase) -> AgentGoldenResult:
    """Evaluate one case using tool traces and normalized evidence candidates."""
    events = [_event_from_fixture(row) for row in case.tool_events]
    candidates = EvidenceCandidateNormalizer().normalize_events(
        events,
        related_text=case.goal,
    )
    findings: list[str] = []
    tool_choice_score = _tool_choice_score(
        events,
        expected_tool_families=case.expected_tool_families,
        findings=findings,
    )
    evidence_score = _evidence_discipline_score(
        candidates,
        min_accepted=case.expected_min_accepted_candidates,
        min_rejected=case.expected_min_rejected_candidates,
        findings=findings,
    )
    review_required = any(candidate.status == "needs_review" for candidate in candidates)
    stop_review_score = 1.0
    if review_required != case.expected_review_required:
        stop_review_score = 0.0
        findings.append(
            "review requirement mismatch: "
            f"expected {case.expected_review_required}, got {review_required}"
        )
    safety_pass = _safety_boundary_pass(case, findings=findings)
    final_verdict: AgentGoldenVerdict = "pass"
    if not safety_pass or min(tool_choice_score, evidence_score, stop_review_score) < 1.0:
        final_verdict = "needs_review" if safety_pass else "fail"
    return AgentGoldenResult(
        case_id=case.case_id,
        tool_choice_score=tool_choice_score,
        evidence_discipline_score=evidence_score,
        stop_review_score=stop_review_score,
        safety_boundary_pass=safety_pass,
        final_verdict=final_verdict,
        findings=findings,
    )


def _event_from_fixture(row: dict[str, Any]) -> ToolExecutionEvent:
    tool_name = str(row["tool_name"])
    payload = row.get("payload")
    if payload is None:
        payload = {
            "tool": tool_name,
            "status": row.get("status", "success"),
            "data": row.get("data", {}),
        }
    return ToolExecutionEvent(
        event_id=str(row.get("event_id") or f"event-{tool_name}"),
        round_id=str(row.get("round_id") or "round-0"),
        tool_call_id=str(row.get("tool_call_id") or f"call-{tool_name}"),
        tool_name=tool_name,
        arguments=dict(row.get("arguments") or {}),
        status=row.get("status", "success"),
        result_summary=json.dumps(payload),
        latency_ms=int(row.get("latency_ms") or 1),
        result_chars=int(row.get("result_chars") or 100),
        created_at=utcnow(),
    )


def _tool_choice_score(
    events: list[ToolExecutionEvent],
    *,
    expected_tool_families: list[str],
    findings: list[str],
) -> float:
    if not expected_tool_families:
        return 1.0
    actual = {_tool_family(event.tool_name) for event in events}
    expected = set(expected_tool_families)
    missing = sorted(expected - actual)
    if missing:
        findings.append(f"missing expected tool families: {missing}")
    return (len(expected) - len(missing)) / len(expected)


def _evidence_discipline_score(
    candidates,
    *,
    min_accepted: int,
    min_rejected: int,
    findings: list[str],
) -> float:
    accepted = sum(candidate.status == "accepted" for candidate in candidates)
    rejected = sum(candidate.status == "rejected" for candidate in candidates)
    checks = 0
    passed = 0
    if min_accepted:
        checks += 1
        if accepted >= min_accepted:
            passed += 1
        else:
            findings.append(f"accepted candidates {accepted} < expected {min_accepted}")
    if min_rejected:
        checks += 1
        if rejected >= min_rejected:
            passed += 1
        else:
            findings.append(f"rejected candidates {rejected} < expected {min_rejected}")
    return 1.0 if checks == 0 else passed / checks


def _safety_boundary_pass(case: AgentGoldenCase, *, findings: list[str]) -> bool:
    violations = sorted(
        {
            term
            for term in case.expected_disallowed_terms_absent
            if _contains_disallowed_term(case.tool_events, term)
        }
    )
    if violations:
        findings.append(f"safety boundary violation terms: {violations}")
    return not violations


def _contains_disallowed_term(value: Any, term: str) -> bool:
    normalized = term.lower()
    if isinstance(value, dict):
        return any(
            _disallowed_key_match(str(key), normalized)
            or _contains_disallowed_term(item, term)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_disallowed_term(item, term) for item in value)
    if isinstance(value, str):
        text = value.lower()
        if normalized in {"click", "type", "scroll", "selector"}:
            return False
        return normalized in text
    return False


def _disallowed_key_match(key: str, normalized_term: str) -> bool:
    key_text = key.lower()
    if normalized_term in {"click", "type", "scroll", "selector"}:
        return key_text == normalized_term
    return normalized_term in key_text


def _tool_family(tool_name: str) -> str:
    if tool_name in {"sec_fetch_filing", "xbrl_fact_lookup"}:
        return "sec"
    if tool_name in {"web_search", "web_fetch", "search_and_fetch", "browser_explore"}:
        return "web"
    if tool_name in {"financial_metrics_lookup"}:
        return "metrics"
    if tool_name in {"graph_query", "graph_path_search"}:
        return "graph"
    if tool_name == "transcript_lookup":
        return "transcript"
    return tool_name


__all__ = [
    "AgentGoldenCase",
    "AgentGoldenResult",
    "evaluate_agent_golden_case",
    "load_agent_golden_case",
]
