"""Idempotent Agent-result recorder and conversation resume helper."""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.messages import ModelMessage

from src.ai.message_store import (
    AgentMessageStore,
    StoredMessageBatch,
    conversation_messages,
    encode_messages,
)


class ResumeContext(BaseModel):
    """A new execution correlated to an existing conversation."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    run_id: str
    conversation_id: str
    message_history: list[Any] = Field(default_factory=list)


class AgentRunRecorder:
    """Persist only the new messages emitted by each successful run."""

    def __init__(self, store: AgentMessageStore) -> None:
        self.store = store

    async def record_result(
        self,
        *,
        run_id: str,
        conversation_id: str,
        agent_name: str,
        result: object,
    ) -> bool:
        messages = list(result.new_messages())  # type: ignore[attr-defined]
        usage_value = result.usage  # type: ignore[attr-defined]
        usage = usage_value() if callable(usage_value) else usage_value
        if dataclasses.is_dataclass(usage):
            usage_payload = dataclasses.asdict(usage)
        elif hasattr(usage, "model_dump"):
            usage_payload = usage.model_dump(mode="json")
        else:
            usage_payload = dict(vars(usage))
        return await self.store.append(
            StoredMessageBatch(
                operation_id=f"{run_id}:{agent_name}",
                conversation_id=conversation_id,
                run_id=run_id,
                agent_name=agent_name,
                messages=encode_messages(messages),
                usage=usage_payload,
            )
        )

    async def resume(self, conversation_id: str) -> ResumeContext:
        history = await self.message_history(conversation_id)
        return ResumeContext(
            run_id=f"resume-{uuid.uuid4().hex[:12]}",
            conversation_id=conversation_id,
            message_history=history,
        )

    async def message_history(
        self, conversation_id: str
    ) -> list[ModelMessage]:
        """Load trusted server-side history for the next Agent request."""
        return await conversation_messages(self.store, conversation_id)


__all__ = ["AgentRunRecorder", "ResumeContext"]
