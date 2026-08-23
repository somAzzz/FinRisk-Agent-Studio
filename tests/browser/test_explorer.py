from datetime import datetime

import pytest

from src.browser.explorer import ExplorationState, Finding, MarketExplorer
from src.browser.wrapper import BrowserWrapper


class FakeBrowserClient:
    async def summarize(self, content: str) -> str:
        return content[:200]

    async def decide_action(self, goal, visited_urls, recent_findings):
        return None


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
    client = FakeBrowserClient()
    explorer = MarketExplorer(client, wrapper)
    assert explorer.llm_client is not None
    assert explorer.wrapper is not None
    wrapper.close()


def test_market_explorer_default_wrapper_uses_factory(monkeypatch):
    class FakeWrapper:
        def close(self):
            pass

    fake_wrapper = FakeWrapper()
    monkeypatch.setattr(
        "src.browser.explorer.build_browser_wrapper",
        lambda *, browser_config: fake_wrapper,
    )
    explorer = MarketExplorer(llm_client=FakeBrowserClient())

    assert explorer.wrapper is fake_wrapper
