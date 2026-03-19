import pytest
from datetime import datetime
from src.browser.explorer import Finding, ExplorationState, MarketExplorer
from src.browser.wrapper import BrowserWrapper


def test_finding_dataclass():
    f = Finding(
        url="https://example.com",
        content_hash="abc123",
        summary="Test summary",
        timestamp=datetime.now(),
        source_type="news",
    )
    assert f.url == "https://example.com"
    assert f.source_type == "news"


def test_exploration_state_dataclass():
    state = ExplorationState(
        goal="Test exploration",
        findings=[],
        visited_urls=set(),
        current_step=0,
        last_discovery=datetime.now(),
    )
    assert state.goal == "Test exploration"
    assert len(state.findings) == 0


@pytest.mark.asyncio
async def test_market_explorer_init():
    wrapper = BrowserWrapper()
    from src.llm.client import EdgarLLMClient
    client = EdgarLLMClient()
    explorer = MarketExplorer(client, wrapper)
    assert explorer.llm_client is not None
    assert explorer.wrapper is not None
    wrapper.close()
