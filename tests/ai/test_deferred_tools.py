"""Deferred approval denial, expiry and replay tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from src.ai.approvals import DeferredApprovalStore, SQLiteDeferredApprovalStore


def _request(store: DeferredApprovalStore):
    return store.request(
        run_id="run-1",
        conversation_id="conversation-1",
        tool_name="graph_write",
        arguments={"node": "company:AAPL"},
        requested_by="agent",
    )


def test_denied_approval_cannot_execute() -> None:
    store = DeferredApprovalStore()
    item = _request(store)
    store.decide(item.approval_id, approve=False, reviewer="reviewer")

    with pytest.raises(PermissionError, match="denied"):
        store.claim_for_execution(
            item.approval_id,
            token=item.decision_token,
            principal="worker",
        )


def test_expired_approval_cannot_execute() -> None:
    store = DeferredApprovalStore()
    item = _request(store)
    store.decide(item.approval_id, approve=True, reviewer="reviewer")
    item.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    with pytest.raises(PermissionError, match="expired"):
        store.claim_for_execution(
            item.approval_id,
            token=item.decision_token,
            principal="worker",
        )


def test_approved_call_is_single_use_and_replay_is_audited() -> None:
    store = DeferredApprovalStore()
    item = _request(store)
    store.decide(item.approval_id, approve=True, reviewer="reviewer")

    claimed = store.claim_for_execution(
        item.approval_id,
        token=item.decision_token,
        principal="worker",
    )
    with pytest.raises(PermissionError, match="executed"):
        store.claim_for_execution(
            item.approval_id,
            token=item.decision_token,
            principal="worker",
        )

    assert claimed.status == "executed"
    assert store.audit_log[-1]["action"] == "execution_rejected"


def test_sqlite_approval_survives_restart_and_rejects_replay(tmp_path) -> None:
    path = tmp_path / "approvals.sqlite3"
    first = SQLiteDeferredApprovalStore(path)
    item = _request(first)
    first.decide(item.approval_id, approve=True, reviewer="reviewer")

    restarted = SQLiteDeferredApprovalStore(path)
    restored = restarted.claim_for_execution(
        item.approval_id,
        token=item.decision_token,
        principal="worker",
    )

    assert restored.status == "executed"
    after_execution = SQLiteDeferredApprovalStore(path)
    with pytest.raises(PermissionError, match="executed"):
        after_execution.claim_for_execution(
            item.approval_id,
            token=item.decision_token,
            principal="worker",
        )
    assert after_execution.audit_log[-1]["action"] == "execution_rejected"


def test_sqlite_approval_allows_only_one_concurrent_claim(tmp_path) -> None:
    path = tmp_path / "approvals.sqlite3"
    first = SQLiteDeferredApprovalStore(path)
    item = _request(first)
    first.decide(item.approval_id, approve=True, reviewer="reviewer")

    def claim(principal: str) -> str:
        store = SQLiteDeferredApprovalStore(path)
        try:
            store.claim_for_execution(
                item.approval_id,
                token=item.decision_token,
                principal=principal,
            )
        except PermissionError:
            return "rejected"
        return "executed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, ["worker-1", "worker-2"]))

    assert sorted(results) == ["executed", "rejected"]
