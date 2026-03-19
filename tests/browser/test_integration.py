import asyncio
import shutil

import pytest

from src.browser import BrowserWrapper, MarketExplorer
from src.llm.client import EdgarLLMClient


def _check_agent_browser():
    return shutil.which("agent-browser") is not None


@pytest.mark.skipif(not _check_agent_browser(), reason="agent-browser CLI not installed")
@pytest.mark.asyncio
async def test_end_to_end_exploration():
    """End-to-end test requires agent-browser CLI installed."""
    wrapper = BrowserWrapper()
    client = EdgarLLMClient()
    explorer = MarketExplorer(client, wrapper)

    checkpoint_calls = []

    def checkpoint_handler(state):
        checkpoint_calls.append(state.current_step)
        # Stop after 1 checkpoint to avoid long test
        return len(checkpoint_calls) < 1

    result = await explorer.explore(
        goal="Find information about Apple's latest earnings",
        checkpoint_callback=checkpoint_handler,
    )

    assert result.goal == "Find information about Apple's latest earnings"
    assert result.current_step > 0

    wrapper.close()
