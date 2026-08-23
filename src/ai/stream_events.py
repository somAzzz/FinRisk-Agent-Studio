"""Redacted projection of Pydantic AI stream events for API consumers."""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.security.redaction import redact_obj


class InternalAgentStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: f"stream-{uuid.uuid4().hex[:12]}")
    sequence: int = Field(ge=0)
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def project_stream_event(event: object, *, sequence: int) -> InternalAgentStreamEvent:
    """Convert any framework event without exposing credentials or raw objects."""
    if dataclasses.is_dataclass(event):
        payload = dataclasses.asdict(event)
    elif hasattr(event, "model_dump"):
        payload = event.model_dump(mode="json")
    else:
        payload = dict(vars(event))
    event_type = str(
        payload.pop("event_kind", None)
        or payload.pop("kind", None)
        or type(event).__name__
    )
    return InternalAgentStreamEvent(
        sequence=sequence,
        event_type=event_type,
        payload=redact_obj(payload),
    )


__all__ = ["InternalAgentStreamEvent", "project_stream_event"]
