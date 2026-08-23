"""Stream-event projection and redaction tests."""

from pydantic_ai import PartStartEvent
from pydantic_ai.messages import TextPart

from src.ai.stream_events import project_stream_event


def test_stream_event_is_typed_and_redacted() -> None:
    event = PartStartEvent(
        index=0,
        part=TextPart(content="OPENAI_API_KEY=sk-secret-value"),
    )

    projected = project_stream_event(event, sequence=3)
    serialized = projected.model_dump_json()

    assert projected.sequence == 3
    assert projected.event_type == "part_start"
    assert "sk-secret-value" not in serialized
