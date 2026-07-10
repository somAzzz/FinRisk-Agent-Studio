"""Human-confirmed post-earnings review drafts tied to immutable snapshots."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.research.change_detection import ResearchChange
from src.research.expectations import ExpectationComparison
from src.research.journal import (
    InvestmentThesis,
    ResearchJournalStore,
    ReviewOutcome,
    ThesisReview,
)
from src.research.models import CompanyResearchSnapshot


class PostEarningsReviewDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    ticker: str
    thesis_id: str
    from_snapshot_id: str
    to_snapshot_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["draft", "confirmed"] = "draft"
    locked_thesis_statement: str
    locked_disconfirming_conditions: list[str]
    locked_assumptions: dict[str, Any] = Field(default_factory=dict)
    changes: list[ResearchChange] = Field(default_factory=list)
    expectation_comparisons: list[ExpectationComparison] = Field(default_factory=list)
    suggested_outcome: ReviewOutcome
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    confirmed_review_id: str | None = None


class PostEarningsDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thesis_id: str
    from_snapshot_id: str
    to_snapshot_id: str
    expectation_ids: list[str] = Field(default_factory=list)
    locked_assumptions: dict[str, Any] = Field(default_factory=dict)


class ConfirmPostEarningsReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: ReviewOutcome
    notes: str


class PostEarningsReviewStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS post_earnings_review_drafts (
                    draft_id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    thesis_id TEXT NOT NULL,
                    from_snapshot_id TEXT NOT NULL,
                    to_snapshot_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE(thesis_id, from_snapshot_id, to_snapshot_id)
                )
                """
            )

    def save(self, draft: PostEarningsReviewDraft) -> PostEarningsReviewDraft:
        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT payload FROM post_earnings_review_drafts
                WHERE thesis_id = ? AND from_snapshot_id = ? AND to_snapshot_id = ?
                """,
                (draft.thesis_id, draft.from_snapshot_id, draft.to_snapshot_id),
            ).fetchone()
            if existing:
                return PostEarningsReviewDraft.model_validate_json(existing["payload"])
            connection.execute(
                """
                INSERT INTO post_earnings_review_drafts
                    (draft_id, ticker, thesis_id, from_snapshot_id, to_snapshot_id,
                     status, generated_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.draft_id,
                    draft.ticker,
                    draft.thesis_id,
                    draft.from_snapshot_id,
                    draft.to_snapshot_id,
                    draft.status,
                    draft.generated_at.isoformat(),
                    draft.model_dump_json(),
                ),
            )
        return draft

    def get(self, draft_id: str) -> PostEarningsReviewDraft | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM post_earnings_review_drafts WHERE draft_id = ?",
                (draft_id,),
            ).fetchone()
        return PostEarningsReviewDraft.model_validate_json(row["payload"]) if row else None

    def list(self, *, ticker: str | None = None) -> list[PostEarningsReviewDraft]:
        query = "SELECT payload FROM post_earnings_review_drafts"
        parameters: tuple[str, ...] = ()
        if ticker:
            query += " WHERE ticker = ?"
            parameters = (ticker.upper().strip(),)
        query += " ORDER BY generated_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [PostEarningsReviewDraft.model_validate_json(row["payload"]) for row in rows]

    def confirm(
        self,
        draft_id: str,
        request: ConfirmPostEarningsReviewRequest,
        journal_store: ResearchJournalStore,
    ) -> PostEarningsReviewDraft:
        draft = self.get(draft_id)
        if draft is None:
            raise KeyError(draft_id)
        if draft.status == "confirmed":
            return draft
        review = ThesisReview(
            outcome=request.outcome,
            notes=request.notes,
            evidence_ids=draft.evidence_ids,
        )
        journal_store.add_review(draft.thesis_id, review)
        confirmed = draft.model_copy(update={"status": "confirmed", "confirmed_review_id": review.review_id})
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE post_earnings_review_drafts
                SET status = ?, payload = ? WHERE draft_id = ?
                """,
                (confirmed.status, confirmed.model_dump_json(), draft_id),
            )
        return confirmed


def build_post_earnings_review_draft(
    *,
    thesis: InvestmentThesis,
    previous: CompanyResearchSnapshot,
    current: CompanyResearchSnapshot,
    changes: list[ResearchChange],
    expectation_comparisons: list[ExpectationComparison] | None = None,
    locked_assumptions: dict[str, Any] | None = None,
) -> PostEarningsReviewDraft:
    if thesis.ticker != previous.ticker or thesis.ticker != current.ticker:
        raise ValueError("thesis and snapshots must belong to the same ticker")
    if previous.as_of >= current.as_of:
        raise ValueError("current snapshot must be newer than previous snapshot")
    comparisons = expectation_comparisons or []
    assumptions = locked_assumptions or {}
    outcome, rationale = _suggest_outcome(thesis, changes)
    evidence_ids = sorted(
        {evidence_id for change in changes for evidence_id in (change.before_evidence_ids + change.after_evidence_ids)}
    )
    identity = json.dumps(
        {
            "thesis_id": thesis.thesis_id,
            "from": previous.snapshot_id,
            "to": current.snapshot_id,
        },
        sort_keys=True,
    )
    return PostEarningsReviewDraft(
        draft_id=f"post-review-{hashlib.sha256(identity.encode()).hexdigest()[:16]}",
        ticker=thesis.ticker,
        thesis_id=thesis.thesis_id,
        from_snapshot_id=previous.snapshot_id,
        to_snapshot_id=current.snapshot_id,
        locked_thesis_statement=thesis.statement,
        locked_disconfirming_conditions=list(thesis.disconfirming_conditions),
        locked_assumptions=assumptions,
        changes=changes,
        expectation_comparisons=comparisons,
        suggested_outcome=outcome,
        rationale=rationale,
        evidence_ids=evidence_ids,
    )


def _suggest_outcome(
    thesis: InvestmentThesis,
    changes: list[ResearchChange],
) -> tuple[ReviewOutcome, str]:
    if not changes:
        return "unknown", "No evidence-linked changes were available for evaluation."
    condition_tokens = {
        token.lower() for condition in thesis.disconfirming_conditions for token in condition.split() if len(token) >= 5
    }
    adverse = [
        change
        for change in changes
        if change.status in {"weakened", "resolved"}
        and condition_tokens.intersection(f"{change.key} {change.explanation}".lower().split())
    ]
    if adverse:
        return (
            "invalidated",
            "One or more adverse changes overlap an explicit disconfirming "
            "condition; analyst confirmation is required.",
        )
    supportive = [
        change for change in changes if change.status == "strengthened" and change.materiality in {"high", "medium"}
    ]
    if supportive and len(supportive) == len(changes):
        return (
            "supported",
            "All material detected changes moved in a supportive direction; analyst confirmation is required.",
        )
    return (
        "mixed",
        "The period contains mixed or incomplete evidence; analyst judgment is required.",
    )


__all__ = [
    "ConfirmPostEarningsReviewRequest",
    "PostEarningsDraftRequest",
    "PostEarningsReviewDraft",
    "PostEarningsReviewStore",
    "build_post_earnings_review_draft",
]
