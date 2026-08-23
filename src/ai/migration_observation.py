"""Release-observation gate for switching the Agent runtime default."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from src.agents.state import AgentRunState


class PrimaryObservationReport(BaseModel):
    """Auditable readiness summary derived only from persisted run state."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    required_runs: int
    required_hours: float
    total_runs: int
    primary_runs: int
    terminal_primary_runs: int
    failed_primary_runs: int
    needs_review_primary_runs: int
    fallback_primary_runs: int
    fallback_event_count: int
    observed_hours: float
    failure_rate: float
    ready: bool
    blockers: list[str] = Field(default_factory=list)
    primary_run_ids: list[str] = Field(default_factory=list)


def evaluate_primary_observation(
    states: list[AgentRunState],
    *,
    required_runs: int = 20,
    required_hours: float = 168.0,
) -> PrimaryObservationReport:
    """Evaluate the documented primary observation and fallback-zero gates."""
    if required_runs <= 0:
        raise ValueError("required_runs must be positive")
    if required_hours < 0:
        raise ValueError("required_hours must not be negative")

    primary = [
        state
        for state in states
        if state.runtime_mode == "pydantic_ai_primary"
    ]
    terminal = [
        state
        for state in primary
        if state.status in {"completed", "failed", "needs_review"}
    ]
    failed = [state for state in primary if state.status == "failed"]
    needs_review = [state for state in primary if state.status == "needs_review"]
    fallback_runs = [state for state in primary if state.fallback_events]
    fallback_event_count = sum(len(state.fallback_events) for state in primary)
    if primary:
        started = min(state.created_at for state in primary)
        ended = max(state.updated_at for state in primary)
        observed_hours = max(0.0, (ended - started).total_seconds() / 3600)
    else:
        observed_hours = 0.0

    blockers: list[str] = []
    if len(primary) < required_runs:
        blockers.append(
            f"primary run count {len(primary)} is below required {required_runs}"
        )
    if observed_hours < required_hours:
        blockers.append(
            f"observation window {observed_hours:.2f}h is below required "
            f"{required_hours:.2f}h"
        )
    nonterminal_count = len(primary) - len(terminal)
    if nonterminal_count:
        blockers.append(f"{nonterminal_count} primary runs are non-terminal")
    if failed:
        blockers.append(f"{len(failed)} primary runs failed")
    if fallback_event_count:
        blockers.append(
            f"{fallback_event_count} primary emergency fallback events were recorded"
        )

    return PrimaryObservationReport(
        required_runs=required_runs,
        required_hours=required_hours,
        total_runs=len(states),
        primary_runs=len(primary),
        terminal_primary_runs=len(terminal),
        failed_primary_runs=len(failed),
        needs_review_primary_runs=len(needs_review),
        fallback_primary_runs=len(fallback_runs),
        fallback_event_count=fallback_event_count,
        observed_hours=round(observed_hours, 4),
        failure_rate=(len(failed) / len(primary) if primary else 0.0),
        ready=not blockers,
        blockers=blockers,
        primary_run_ids=[state.run_id for state in primary],
    )


__all__ = ["PrimaryObservationReport", "evaluate_primary_observation"]
