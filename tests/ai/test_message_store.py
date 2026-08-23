"""Versioned message persistence and backward-compatibility tests."""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from src.ai.message_store import (
    InMemoryAgentMessageStore,
    SQLiteAgentMessageStore,
    StoredMessageBatch,
    conversation_messages,
    encode_messages,
)
from src.api.run_store import FinRiskSQLiteRunStore
from src.workflows.state import FinRiskRequest, FinRiskWorkflowState


async def _messages():
    result = await Agent(TestModel(), output_type=str).run("hello")
    return result.all_messages()


async def test_message_history_round_trips_framework_types() -> None:
    messages = await _messages()
    store = InMemoryAgentMessageStore()
    batch = StoredMessageBatch(
        operation_id="op-1",
        conversation_id="conversation-1",
        run_id="run-1",
        agent_name="test-agent",
        messages=encode_messages(messages),
    )

    assert await store.append(batch) is True
    assert await store.append(batch.model_copy()) is False
    restored = await conversation_messages(store, "conversation-1")

    assert [type(item) for item in restored] == [type(item) for item in messages]
    assert encode_messages(restored) == encode_messages(messages)

    continued = await Agent(TestModel(), output_type=str).run(
        "continue", message_history=restored
    )
    assert continued.output


async def test_sqlite_store_survives_new_instance(tmp_path) -> None:
    path = tmp_path / "messages.sqlite3"
    messages = await _messages()
    first = SQLiteAgentMessageStore(path)
    await first.append(
        StoredMessageBatch(
            operation_id="op-sqlite",
            conversation_id="conversation-sqlite",
            run_id="run-sqlite",
            agent_name="test-agent",
            messages=encode_messages(messages),
        )
    )

    restored = await conversation_messages(
        SQLiteAgentMessageStore(path), "conversation-sqlite"
    )

    assert encode_messages(restored) == encode_messages(messages)


async def test_additive_message_table_keeps_legacy_run_readable(tmp_path) -> None:
    path = tmp_path / "shared.sqlite3"
    legacy_store = FinRiskSQLiteRunStore(path)
    state = FinRiskWorkflowState(
        run_id="legacy-run",
        request=FinRiskRequest(
            ticker="AAPL", analysis_goal="Review evidence", demo_mode=True
        ),
    )
    await legacy_store.update(state)
    await legacy_store.close()

    await SQLiteAgentMessageStore(path).append(
        StoredMessageBatch(
            operation_id="new-message-op",
            conversation_id="conversation-new",
            run_id="new-run",
            agent_name="new-agent",
            messages=encode_messages(await _messages()),
        )
    )

    reopened = FinRiskSQLiteRunStore(path)
    restored = await reopened.get("legacy-run")
    await reopened.close()
    assert restored is not None
    assert restored.request.ticker == "AAPL"
