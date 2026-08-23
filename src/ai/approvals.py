"""Server-side deferred approval with expiry and replay protection."""

from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ApprovalStatus = Literal[
    "pending", "approved", "denied", "expired", "cancelled", "executed"
]


class DeferredToolApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str
    run_id: str
    conversation_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    requested_by: str
    status: ApprovalStatus = "pending"
    expires_at: datetime
    decided_by: str | None = None
    decision_reason: str | None = None
    decision_token: str = Field(default_factory=lambda: secrets.token_urlsafe(24))


class DeferredApprovalStore:
    """In-memory reference implementation with atomic single-use claims."""

    def __init__(self) -> None:
        self._items: dict[str, DeferredToolApproval] = {}
        self.audit_log: list[dict[str, Any]] = []

    def request(
        self,
        *,
        run_id: str,
        conversation_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        requested_by: str,
        ttl_seconds: int = 300,
    ) -> DeferredToolApproval:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        approval = DeferredToolApproval(
            approval_id=f"approval-{secrets.token_hex(8)}",
            run_id=run_id,
            conversation_id=conversation_id,
            tool_name=tool_name,
            arguments=arguments,
            requested_by=requested_by,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        self._items[approval.approval_id] = approval
        self._audit(approval, "requested")
        return approval

    def decide(
        self,
        approval_id: str,
        *,
        approve: bool,
        reviewer: str,
        reason: str | None = None,
    ) -> DeferredToolApproval:
        item = self._require_pending(approval_id)
        item.status = "approved" if approve else "denied"
        item.decided_by = reviewer
        item.decision_reason = reason
        self._audit(item, item.status)
        return item

    def claim_for_execution(
        self, approval_id: str, *, token: str, principal: str
    ) -> DeferredToolApproval:
        item = self._require(approval_id)
        self._expire_if_needed(item)
        if item.status != "approved":
            self._audit(item, "execution_rejected", principal=principal)
            raise PermissionError(f"approval is {item.status}, not approved")
        if not secrets.compare_digest(item.decision_token, token):
            self._audit(item, "token_rejected", principal=principal)
            raise PermissionError("invalid approval token")
        item.status = "executed"
        self._audit(item, "executed", principal=principal)
        return item

    def cancel(self, approval_id: str, *, principal: str) -> DeferredToolApproval:
        item = self._require_pending(approval_id)
        item.status = "cancelled"
        self._audit(item, "cancelled", principal=principal)
        return item

    def _require_pending(self, approval_id: str) -> DeferredToolApproval:
        item = self._require(approval_id)
        self._expire_if_needed(item)
        if item.status != "pending":
            raise PermissionError(f"approval is {item.status}, not pending")
        return item

    def _require(self, approval_id: str) -> DeferredToolApproval:
        try:
            return self._items[approval_id]
        except KeyError as exc:
            raise KeyError(f"unknown approval {approval_id!r}") from exc

    def _expire_if_needed(self, item: DeferredToolApproval) -> None:
        if item.status in {"pending", "approved"} and datetime.now(UTC) >= item.expires_at:
            item.status = "expired"
            self._audit(item, "expired")

    def _audit(
        self, item: DeferredToolApproval, action: str, **metadata: Any
    ) -> None:
        self.audit_log.append(
            {
                "approval_id": item.approval_id,
                "run_id": item.run_id,
                "action": action,
                "status": item.status,
                "timestamp": datetime.now(UTC).isoformat(),
                **metadata,
            }
        )


class SQLiteDeferredApprovalStore(DeferredApprovalStore):
    """Additive durable approval store with restart-safe replay protection."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__()
        self._initialize()
        self._load()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS deferred_tool_approvals (
                    approval_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS deferred_tool_approval_audit (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    approval_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    def _load(self) -> None:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT payload FROM deferred_tool_approvals"
            ).fetchall()
            self._items = {
                item.approval_id: item
                for item in (
                    DeferredToolApproval.model_validate_json(row[0])
                    for row in rows
                )
            }
            audit_rows = connection.execute(
                """
                SELECT payload FROM deferred_tool_approval_audit
                ORDER BY sequence
                """
            ).fetchall()
            self.audit_log = [json.loads(row[0]) for row in audit_rows]
        finally:
            connection.close()

    def _audit(
        self, item: DeferredToolApproval, action: str, **metadata: Any
    ) -> None:
        super()._audit(item, action, **metadata)
        connection = self._connect()
        try:
            self._persist(connection, item, self.audit_log[-1])
            connection.commit()
        finally:
            connection.close()

    def decide(
        self,
        approval_id: str,
        *,
        approve: bool,
        reviewer: str,
        reason: str | None = None,
    ) -> DeferredToolApproval:
        connection, item = self._begin_current(approval_id)
        try:
            self._require_current_pending(connection, item)
            item.status = "approved" if approve else "denied"
            item.decided_by = reviewer
            item.decision_reason = reason
            self._commit_action(connection, item, item.status)
            return item
        finally:
            connection.close()

    def claim_for_execution(
        self, approval_id: str, *, token: str, principal: str
    ) -> DeferredToolApproval:
        connection, item = self._begin_current(approval_id)
        try:
            if self._expire_current(connection, item):
                raise PermissionError("approval is expired, not approved")
            if item.status != "approved":
                self._commit_action(
                    connection, item, "execution_rejected", principal=principal
                )
                raise PermissionError(f"approval is {item.status}, not approved")
            if not secrets.compare_digest(item.decision_token, token):
                self._commit_action(
                    connection, item, "token_rejected", principal=principal
                )
                raise PermissionError("invalid approval token")
            item.status = "executed"
            self._commit_action(connection, item, "executed", principal=principal)
            return item
        finally:
            connection.close()

    def cancel(self, approval_id: str, *, principal: str) -> DeferredToolApproval:
        connection, item = self._begin_current(approval_id)
        try:
            self._require_current_pending(connection, item)
            item.status = "cancelled"
            self._commit_action(connection, item, "cancelled", principal=principal)
            return item
        finally:
            connection.close()

    def _begin_current(
        self, approval_id: str
    ) -> tuple[sqlite3.Connection, DeferredToolApproval]:
        connection = self._connect()
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT payload FROM deferred_tool_approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        if row is None:
            connection.rollback()
            connection.close()
            raise KeyError(f"unknown approval {approval_id!r}")
        return connection, DeferredToolApproval.model_validate_json(row[0])

    def _require_current_pending(
        self, connection: sqlite3.Connection, item: DeferredToolApproval
    ) -> None:
        if self._expire_current(connection, item):
            raise PermissionError("approval is expired, not pending")
        if item.status != "pending":
            connection.rollback()
            raise PermissionError(f"approval is {item.status}, not pending")

    def _expire_current(
        self, connection: sqlite3.Connection, item: DeferredToolApproval
    ) -> bool:
        if item.status in {"pending", "approved"} and datetime.now(UTC) >= item.expires_at:
            item.status = "expired"
            self._commit_action(connection, item, "expired")
            return True
        return False

    def _commit_action(
        self,
        connection: sqlite3.Connection,
        item: DeferredToolApproval,
        action: str,
        **metadata: Any,
    ) -> None:
        entry = {
            "approval_id": item.approval_id,
            "run_id": item.run_id,
            "action": action,
            "status": item.status,
            "timestamp": datetime.now(UTC).isoformat(),
            **metadata,
        }
        self._persist(connection, item, entry)
        connection.commit()
        self._items[item.approval_id] = item
        self.audit_log.append(entry)

    @staticmethod
    def _persist(
        connection: sqlite3.Connection,
        item: DeferredToolApproval,
        entry: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO deferred_tool_approvals
            (approval_id, payload) VALUES (?, ?)
            """,
            (item.approval_id, item.model_dump_json()),
        )
        connection.execute(
            """
            INSERT INTO deferred_tool_approval_audit
            (approval_id, payload) VALUES (?, ?)
            """,
            (item.approval_id, json.dumps(entry, ensure_ascii=False)),
        )


__all__ = [
    "DeferredApprovalStore",
    "DeferredToolApproval",
    "SQLiteDeferredApprovalStore",
]
