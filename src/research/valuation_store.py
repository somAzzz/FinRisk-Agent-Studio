"""Immutable history of analyst valuation assumptions and calculated outputs."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.research.database import apply_migrations

ValuationKind = Literal["scenario", "sensitivity", "multiple", "dcf"]


class ValuationAssumptionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumption_snapshot_id: str
    ticker: str
    kind: ValuationKind
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    request: dict[str, Any]
    result: dict[str, Any]
    evidence_ids: list[str] = Field(default_factory=list)


class ValuationAssumptionStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        apply_migrations(self.path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def save(
        self,
        *,
        ticker: str,
        kind: ValuationKind,
        request: dict[str, Any],
        result: dict[str, Any],
        evidence_ids: list[str],
    ) -> ValuationAssumptionSnapshot:
        snapshot = ValuationAssumptionSnapshot(
            assumption_snapshot_id=f"valuation-{uuid.uuid4().hex[:16]}",
            ticker=ticker.upper().strip(),
            kind=kind,
            request=request,
            result=result,
            evidence_ids=sorted(set(evidence_ids)),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO research_valuation_assumptions VALUES (?, ?, ?, ?, ?)",
                (
                    snapshot.assumption_snapshot_id,
                    snapshot.ticker,
                    snapshot.kind,
                    snapshot.created_at.isoformat(),
                    snapshot.model_dump_json(),
                ),
            )
        return snapshot

    def list(self, ticker: str, *, limit: int = 100) -> list[ValuationAssumptionSnapshot]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM research_valuation_assumptions
                WHERE ticker = ? ORDER BY created_at DESC LIMIT ?
                """,
                (ticker.upper().strip(), limit),
            ).fetchall()
        return [
            ValuationAssumptionSnapshot.model_validate_json(row["payload"])
            for row in rows
        ]


__all__ = ["ValuationAssumptionSnapshot", "ValuationAssumptionStore"]
