"""Idempotency and ordering tests for graph branch reducers."""

from dataclasses import dataclass

from src.ai.graphs.reducers import merge_unique_sorted


@dataclass(frozen=True)
class Row:
    row_id: str
    value: str


def test_merge_is_stable_and_idempotent() -> None:
    first = [Row("b", "first-b"), Row("a", "first-a")]
    second = [Row("c", "second-c"), Row("b", "second-b")]

    once = merge_unique_sorted([first, second], key=lambda row: row.row_id)
    twice = merge_unique_sorted([once, once], key=lambda row: row.row_id)

    assert [row.row_id for row in once] == ["a", "b", "c"]
    assert once[1].value == "first-b"
    assert twice == once


def test_empty_or_failed_branch_can_be_omitted_without_losing_successes() -> None:
    successful = [Row("evidence-1", "kept")]

    merged = merge_unique_sorted(
        [[], successful, []], key=lambda row: row.row_id
    )

    assert merged == successful
