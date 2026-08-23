"""Tests proving unsafe workflow fan-out cannot be enabled accidentally."""

import pytest

from src.ai.graphs.parallel_policy import (
    FINRISK_PARALLEL_CANDIDATES,
    NodeAccess,
    UnsafeParallelPlanError,
    validate_parallel_group,
)


def test_current_filing_market_pair_is_rejected_as_read_after_write() -> None:
    with pytest.raises(UnsafeParallelPlanError, match="filing_risks"):
        validate_parallel_group(FINRISK_PARALLEL_CANDIDATES)


def test_independent_snapshot_branches_are_allowed() -> None:
    validate_parallel_group(
        [
            NodeAccess(
                node_id="filing_fetch",
                reads=frozenset({"company"}),
                writes=frozenset({"filing_snapshot"}),
            ),
            NodeAccess(
                node_id="transcript_fetch",
                reads=frozenset({"company"}),
                writes=frozenset({"transcript_snapshot"}),
            ),
        ]
    )


def test_shared_trace_write_is_rejected_without_branch_local_buffers() -> None:
    with pytest.raises(UnsafeParallelPlanError, match="trace"):
        validate_parallel_group(
            [
                NodeAccess("one", frozenset(), frozenset({"trace"})),
                NodeAccess("two", frozenset(), frozenset({"trace"})),
            ]
        )
