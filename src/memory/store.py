"""SQLite-backed memory store for v19 context management."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.memory.models import MemoryItem, MemoryStatus, utcnow
from src.memory.rankers import extract_terms


class MemoryStore:
    """Small SQLite store for MemoryItem records."""

    def __init__(self, cache_dir: Path | str | None = None, db_name: str = "memory.sqlite"):
        root = Path(cache_dir) if cache_dir is not None else get_settings().cache_dir
        root.mkdir(parents=True, exist_ok=True)
        self._db_path = root / db_name
        self._lock = threading.Lock()
        self._ensure_schema()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_items (
                        memory_id TEXT PRIMARY KEY,
                        hash TEXT NOT NULL UNIQUE,
                        status TEXT NOT NULL,
                        item_json TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memory_status ON memory_items(status)"
                )
                conn.commit()
            finally:
                conn.close()

    def upsert(self, item: MemoryItem) -> MemoryItem:
        """Insert or update a memory item, deduping by hash."""
        now_ts = int(utcnow().timestamp())
        existing = self._get_by_hash(item.hash)
        if existing is not None:
            item = item.model_copy(
                update={
                    "memory_id": existing.memory_id,
                    "first_seen_at": existing.first_seen_at,
                    "last_seen_at": utcnow(),
                    "last_used_at": existing.last_used_at,
                }
            )
        payload = item.model_dump(mode="json")
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO memory_items (
                        memory_id, hash, status, item_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(memory_id) DO UPDATE SET
                        hash = excluded.hash,
                        status = excluded.status,
                        item_json = excluded.item_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        item.memory_id,
                        item.hash,
                        item.status,
                        json.dumps(payload, ensure_ascii=False),
                        now_ts,
                        now_ts,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return item

    def get(self, memory_id: str) -> MemoryItem | None:
        """Return one memory item by id."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT item_json FROM memory_items WHERE memory_id = ?",
                    (memory_id,),
                ).fetchone()
            finally:
                conn.close()
        return _row_to_item(row)

    def search_candidates(
        self,
        *,
        subject: dict[str, Any] | None = None,
        intent: str = "",
        limit: int = 50,
        include_rejected: bool = False,
    ) -> list[MemoryItem]:
        """Return memory candidates matching subject terms."""
        terms = extract_terms([subject or {}, intent])
        rows = self._load_all()
        items = [_row_to_item(row) for row in rows]
        filtered = [
            item
            for item in items
            if item is not None
            and (include_rejected or item.status not in {"rejected", "deprecated"})
        ]
        if not terms:
            return filtered[:limit]

        def score(item: MemoryItem) -> tuple[int, float]:
            haystack = extract_terms(
                [
                    item.text,
                    item.summary or "",
                    item.entities,
                    item.tickers,
                    item.products,
                    item.risks,
                    item.source_title or "",
                ]
            )
            return (len(terms & haystack), item.credibility_score)

        filtered.sort(key=score, reverse=True)
        return filtered[:limit]

    def mark_used(self, memory_id: str) -> MemoryItem | None:
        """Mark one memory item as used."""
        return self._transition(memory_id, "used", {"last_used_at": utcnow()})

    def mark_rejected(self, memory_id: str, reason: str) -> MemoryItem | None:
        """Mark one memory item as rejected."""
        return self._transition(memory_id, "rejected", {"provenance_reason": reason})

    def mark_stale(self, memory_id: str, reason: str) -> MemoryItem | None:
        """Mark one memory item as stale."""
        return self._transition(memory_id, "stale", {"provenance_reason": reason})

    def list_by_entity(self, entity: str) -> list[MemoryItem]:
        """Return memory items where ``entity`` appears in extracted entities/products/tickers."""
        term = entity.lower().strip()
        items = [_row_to_item(row) for row in self._load_all()]
        result: list[MemoryItem] = []
        for item in items:
            if item is None:
                continue
            values = [*item.entities, *item.products, *item.tickers, item.text]
            if any(term in value.lower() for value in values):
                result.append(item)
        return result

    def list_by_run(self, run_id: str) -> list[MemoryItem]:
        """Return memory items created or used by a workflow run."""
        items = [_row_to_item(row) for row in self._load_all()]
        return [
            item
            for item in items
            if item is not None
            and (
                item.provenance.get("run_id") == run_id
                or run_id in item.provenance.get("run_ids", [])
            )
        ]

    def clear(self) -> None:
        """Delete all memory rows. Intended for tests."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM memory_items")
                conn.commit()
            finally:
                conn.close()

    def _transition(
        self,
        memory_id: str,
        status: MemoryStatus,
        extra: dict[str, Any] | None = None,
    ) -> MemoryItem | None:
        item = self.get(memory_id)
        if item is None:
            return None
        provenance = dict(item.provenance)
        if extra:
            reason = extra.pop("provenance_reason", None)
            if reason:
                provenance.setdefault("status_reasons", []).append(
                    {"status": status, "reason": reason}
                )
            provenance.update(extra)
        updated = item.model_copy(
            update={
                "status": status,
                "last_seen_at": utcnow(),
                "last_used_at": utcnow() if status == "used" else item.last_used_at,
                "provenance": provenance,
            }
        )
        return self.upsert(updated)

    def _get_by_hash(self, item_hash: str) -> MemoryItem | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT item_json FROM memory_items WHERE hash = ?",
                    (item_hash,),
                ).fetchone()
            finally:
                conn.close()
        return _row_to_item(row)

    def _load_all(self) -> list[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT item_json FROM memory_items ORDER BY updated_at DESC"
                ).fetchall()
            finally:
                conn.close()
        return list(rows)


def _row_to_item(row: sqlite3.Row | None) -> MemoryItem | None:
    if row is None:
        return None
    try:
        return MemoryItem.model_validate(json.loads(row["item_json"]))
    except Exception:
        return None


__all__ = ["MemoryStore"]
