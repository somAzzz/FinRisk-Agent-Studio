"""Primary-runtime release observation gate tests."""

from datetime import UTC, datetime, timedelta

from src.agents.state import AgentRunState
from src.ai.migration_observation import evaluate_primary_observation


def _primary_run(
    index: int,
    *,
    created_at: datetime,
    updated_at: datetime,
    status: str = "completed",
    fallback_events: list[str] | None = None,
) -> AgentRunState:
    return AgentRunState(
        run_id=f"primary-{index}",
        user_goal="Observe primary runtime",
        runtime_mode="pydantic_ai_primary",
        status=status,  # type: ignore[arg-type]
        fallback_events=fallback_events or [],
        created_at=created_at,
        updated_at=updated_at,
    )


def test_primary_observation_is_ready_after_clean_release_window() -> None:
    start = datetime(2026, 8, 1, tzinfo=UTC)
    states = [
        _primary_run(
            index,
            created_at=start + timedelta(hours=index),
            updated_at=start + timedelta(hours=168, minutes=index),
        )
        for index in range(20)
    ]

    report = evaluate_primary_observation(states)

    assert report.ready is True
    assert report.primary_runs == 20
    assert report.observed_hours >= 168
    assert report.fallback_event_count == 0


def test_primary_observation_blocks_failure_fallback_and_short_window() -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    states = [
        _primary_run(
            1,
            created_at=now,
            updated_at=now + timedelta(hours=1),
            status="failed",
            fallback_events=["legacy emergency fallback"],
        )
    ]

    report = evaluate_primary_observation(
        states, required_runs=1, required_hours=24
    )

    assert report.ready is False
    assert report.failed_primary_runs == 1
    assert report.fallback_event_count == 1
    assert len(report.blockers) == 3


def test_legacy_state_without_runtime_mode_remains_readable() -> None:
    state = AgentRunState.model_validate(
        {"run_id": "old-run", "user_goal": "Read old state"}
    )

    assert state.runtime_mode == "legacy"
