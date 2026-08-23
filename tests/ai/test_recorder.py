"""Idempotent recorder and resume-correlation tests."""

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from src.ai.message_store import InMemoryAgentMessageStore
from src.ai.recorder import AgentRunRecorder


async def test_recorder_is_idempotent_and_resume_mints_new_run_id() -> None:
    result = await Agent(TestModel(), output_type=str).run("remember this")
    recorder = AgentRunRecorder(InMemoryAgentMessageStore())

    first = await recorder.record_result(
        run_id="run-original",
        conversation_id="conversation-1",
        agent_name="test-agent",
        result=result,
    )
    second = await recorder.record_result(
        run_id="run-original",
        conversation_id="conversation-1",
        agent_name="test-agent",
        result=result,
    )
    resume = await recorder.resume("conversation-1")

    assert first is True
    assert second is False
    assert resume.run_id.startswith("resume-")
    assert resume.run_id != "run-original"
    assert resume.conversation_id == "conversation-1"
    assert resume.message_history
