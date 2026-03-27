import pytest
from unittest.mock import patch, MagicMock
from src.tools.router import ToolRouter, ToolChoice

def test_tool_choice_accepts_time_range():
    """ToolChoice accepts time_range field."""
    choice = ToolChoice(
        thought="Recent news about X",
        tool="ddgs",
        query="latest news",
        time_range="w"
    )
    assert choice.time_range == "w"

def test_tool_choice_time_range_none():
    """ToolChoice time_range defaults to None."""
    choice = ToolChoice(
        thought="General query",
        tool="ddgs",
        query="What is AI"
    )
    assert choice.time_range is None

def test_router_routes_simple_query_to_ddgs_without_llm():
    """Simple query should route to ddgs without LLM call."""
    with patch("src.tools.router.SGLangClient") as mock_llm:
        router = ToolRouter(llm_client=mock_llm)
        choice = router.select_tool("What is Apple's stock ticker?")
        assert choice.tool == "ddgs"
        assert "Rule-based" in choice.thought
        mock_llm.return_value.client.chat.completions.parse.assert_not_called()

def test_router_routes_deep_search_to_tavily_without_llm():
    """Deep search query should route to tavily without LLM call."""
    with patch("src.tools.router.SGLangClient") as mock_llm:
        router = ToolRouter(llm_client=mock_llm)
        choice = router.select_tool("Apple Q1 2026 earnings analysis")
        assert choice.tool == "tavily"
        assert "Rule-based" in choice.thought
        mock_llm.return_value.client.chat.completions.parse.assert_not_called()

def test_router_routes_url_to_web_fetch():
    """URL input should route to web_fetch."""
    with patch("src.tools.router.SGLangClient") as mock_llm:
        router = ToolRouter(llm_client=mock_llm)
        choice = router.select_tool("https://seekingalpha.com/article/123")
        assert choice.tool == "web_fetch"
        assert "Direct URL" in choice.thought
        mock_llm.return_value.client.chat.completions.parse.assert_not_called()