"""Persistent, analyst-confirmed peer groups for comparable-company work."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.research.database import apply_migrations

IndustryTemplate = Literal["general", "bank", "saas", "semiconductor", "energy", "biotech"]
CurrencyPolicy = Literal["original", "single_currency", "no_conversion"]
FiscalPeriodPolicy = Literal["latest_quarter", "calendarized_ttm", "latest_fy"]


class PeerMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    inclusion_reason: str
    source: Literal["user", "suggested"] = "user"
    confirmed_by_user: bool = True

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        cleaned = value.upper().strip()
        if not cleaned:
            raise ValueError("ticker must not be empty")
        return cleaned


class PeerGroupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    base_ticker: str
    members: list[PeerMember] = Field(min_length=2, max_length=30)
    industry_template: IndustryTemplate = "general"
    currency_policy: CurrencyPolicy = "no_conversion"
    fiscal_period_policy: FiscalPeriodPolicy = "calendarized_ttm"
    user_notes: str | None = Field(default=None, max_length=4000)

    @field_validator("base_ticker")
    @classmethod
    def _base_ticker(cls, value: str) -> str:
        return value.upper().strip()

    @model_validator(mode="after")
    def _unique_members(self) -> PeerGroupInput:
        tickers = [member.ticker for member in self.members]
        if len(tickers) != len(set(tickers)):
            raise ValueError("peer group members must be unique")
        if self.base_ticker not in tickers:
            raise ValueError("base_ticker must be included in members")
        if any(member.source == "suggested" and not member.confirmed_by_user for member in self.members):
            raise ValueError("suggested peers must be confirmed before saving")
        return self


class PeerGroup(PeerGroupInput):
    peer_group_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PeerCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tickers: list[str] = Field(default_factory=list, max_length=50)


class PeerCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    company_name: str | None = None
    sic: str | None = None
    sic_description: str | None = None
    similarity: Literal["same_sic", "same_sic_division"]
    inclusion_reason: str
    confirmed_by_user: bool = False


class PeerGroupStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        apply_migrations(self.path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def save(self, value: PeerGroupInput) -> PeerGroup:
        now = datetime.now(UTC)
        group = PeerGroup(
            **value.model_dump(),
            peer_group_id=f"peer-{uuid.uuid4().hex[:16]}",
            created_at=now,
            updated_at=now,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO research_peer_groups VALUES (?, ?, ?, ?, ?)",
                (group.peer_group_id, group.name, group.base_ticker, now.isoformat(), group.model_dump_json()),
            )
        return group

    def list(self) -> list[PeerGroup]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM research_peer_groups ORDER BY updated_at DESC"
            ).fetchall()
        return [PeerGroup.model_validate_json(row["payload"]) for row in rows]

    def update(self, peer_group_id: str, value: PeerGroupInput) -> PeerGroup:
        existing = self.get(peer_group_id)
        if existing is None:
            raise KeyError(peer_group_id)
        updated = PeerGroup(
            **value.model_dump(),
            peer_group_id=peer_group_id,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC),
        )
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE research_peer_groups
                SET name = ?, base_ticker = ?, updated_at = ?, payload = ?
                WHERE peer_group_id = ?
                """,
                (
                    updated.name,
                    updated.base_ticker,
                    updated.updated_at.isoformat(),
                    updated.model_dump_json(),
                    peer_group_id,
                ),
            )
        return updated

    def get(self, peer_group_id: str) -> PeerGroup | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM research_peer_groups WHERE peer_group_id = ?",
                (peer_group_id,),
            ).fetchone()
        return PeerGroup.model_validate_json(row["payload"]) if row else None

    def delete(self, peer_group_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM research_peer_groups WHERE peer_group_id = ?",
                (peer_group_id,),
            )
        return cursor.rowcount > 0


def suggest_peer_candidates(
    *,
    base_ticker: str,
    candidate_tickers: list[str],
    resolver: object,
    submissions_fetcher: Callable[[str], dict],
) -> list[PeerCandidate]:
    """Suggest SEC SIC peers; candidates remain unconfirmed and cannot be saved."""
    base_identity = resolver.resolve(base_ticker)
    if base_identity is None:
        raise LookupError(f"ticker not resolved: {base_ticker}")
    base_submission = submissions_fetcher(base_identity.cik)
    base_sic = str(base_submission.get("sic") or "").strip()
    if not base_sic:
        return []
    candidates: list[PeerCandidate] = []
    for ticker in sorted({item.upper().strip() for item in candidate_tickers}):
        if not ticker or ticker == base_ticker.upper().strip():
            continue
        identity = resolver.resolve(ticker)
        if identity is None:
            continue
        submission = submissions_fetcher(identity.cik)
        sic = str(submission.get("sic") or "").strip()
        if sic == base_sic:
            similarity: Literal["same_sic", "same_sic_division"] = "same_sic"
        elif sic and sic[:2] == base_sic[:2]:
            similarity = "same_sic_division"
        else:
            continue
        description = str(submission.get("sicDescription") or "").strip() or None
        candidates.append(
            PeerCandidate(
                ticker=ticker,
                company_name=getattr(identity, "name", None),
                sic=sic,
                sic_description=description,
                similarity=similarity,
                inclusion_reason=(
                    f"SEC SIC {sic} ({description or 'description unavailable'}); "
                    f"candidate requires analyst confirmation."
                ),
            )
        )
    rank = {"same_sic": 0, "same_sic_division": 1}
    return sorted(candidates, key=lambda item: (rank[item.similarity], item.ticker))


__all__ = [
    "PeerCandidate",
    "PeerCandidateRequest",
    "PeerGroup",
    "PeerGroupInput",
    "PeerGroupStore",
    "PeerMember",
    "suggest_peer_candidates",
]
