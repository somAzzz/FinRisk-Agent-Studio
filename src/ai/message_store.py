"""Versioned Pydantic AI message persistence with idempotent appends."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter


class MessageReplayError(RuntimeError):
    """Raised when an idempotency key is reused with different content."""


class StoredMessageBatch(BaseModel):
    """Append-only, versioned message batch for one Agent execution."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    operation_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def decoded_messages(self) -> list[ModelMessage]:
        payload = json.dumps(self.messages, ensure_ascii=False).encode()
        return ModelMessagesTypeAdapter.validate_json(payload)


class AgentMessageStore(Protocol):
    async def append(self, batch: StoredMessageBatch) -> bool: ...

    async def list_conversation(
        self, conversation_id: str
    ) -> list[StoredMessageBatch]: ...


class InMemoryAgentMessageStore:
    """Process-local append-only message store for tests and demos."""

    def __init__(self) -> None:
        self._batches: dict[str, StoredMessageBatch] = {}
        self._lock = asyncio.Lock()

    async def append(self, batch: StoredMessageBatch) -> bool:
        async with self._lock:
            existing = self._batches.get(batch.operation_id)
            if existing is not None:
                if _semantic_batch(existing) != _semantic_batch(batch):
                    raise MessageReplayError(
                        f"operation_id {batch.operation_id!r} was replayed"
                    )
                return False
            self._batches[batch.operation_id] = batch
            return True

    async def list_conversation(
        self, conversation_id: str
    ) -> list[StoredMessageBatch]:
        return sorted(
            (
                item
                for item in self._batches.values()
                if item.conversation_id == conversation_id
            ),
            key=lambda item: (item.created_at, item.operation_id),
        )


class SQLiteAgentMessageStore:
    """Additive SQLite store that does not alter legacy run tables."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = asyncio.Lock()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_message_batches (
                operation_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        return connection

    def _append_sync(self, batch: StoredMessageBatch) -> bool:
        connection = self._connect()
        try:
            existing = connection.execute(
                "SELECT payload FROM agent_message_batches WHERE operation_id = ?",
                (batch.operation_id,),
            ).fetchone()
            payload = batch.model_dump_json()
            if existing is not None:
                stored = StoredMessageBatch.model_validate_json(existing[0])
                if _semantic_batch(stored) != _semantic_batch(batch):
                    raise MessageReplayError(
                        f"operation_id {batch.operation_id!r} was replayed"
                    )
                return False
            connection.execute(
                "INSERT INTO agent_message_batches VALUES (?, ?, ?, ?)",
                (
                    batch.operation_id,
                    batch.conversation_id,
                    batch.created_at.isoformat(),
                    payload,
                ),
            )
            connection.commit()
            return True
        finally:
            connection.close()

    def _list_sync(self, conversation_id: str) -> list[StoredMessageBatch]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT payload FROM agent_message_batches
                WHERE conversation_id = ?
                ORDER BY created_at, operation_id
                """,
                (conversation_id,),
            ).fetchall()
            return [StoredMessageBatch.model_validate_json(row[0]) for row in rows]
        finally:
            connection.close()

    async def append(self, batch: StoredMessageBatch) -> bool:
        async with self._lock:
            return await asyncio.to_thread(self._append_sync, batch)

    async def list_conversation(
        self, conversation_id: str
    ) -> list[StoredMessageBatch]:
        async with self._lock:
            return await asyncio.to_thread(self._list_sync, conversation_id)


def encode_messages(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    """Serialize framework messages into a JSON-compatible stable field."""
    payload = ModelMessagesTypeAdapter.dump_json(messages)
    value = json.loads(payload)
    if not isinstance(value, list):
        raise TypeError("Pydantic AI message payload must be a list")
    return value


def _semantic_batch(batch: StoredMessageBatch) -> dict[str, Any]:
    return batch.model_dump(mode="json", exclude={"created_at"})


async def conversation_messages(
    store: AgentMessageStore, conversation_id: str
) -> list[ModelMessage]:
    """Restore ordered framework messages for conversation continuation."""
    batches = await store.list_conversation(conversation_id)
    return [message for batch in batches for message in batch.decoded_messages()]


__all__ = [
    "AgentMessageStore",
    "InMemoryAgentMessageStore",
    "MessageReplayError",
    "SQLiteAgentMessageStore",
    "StoredMessageBatch",
    "conversation_messages",
    "encode_messages",
]
