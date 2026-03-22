import pytest
from src.tools.router import ToolChoice

def test_tool_choice_accepts_time_range():
    """ToolChoice accepts time_range field."""
    choice = ToolChoice(
        thought="Recent news about X",
        tool="web_search",
        query="latest news",
        time_range="w"
    )
    assert choice.time_range == "w"

def test_tool_choice_time_range_none():
    """ToolChoice time_range defaults to None."""
    choice = ToolChoice(
        thought="General query",
        tool="web_search",
        query="What is AI"
    )
    assert choice.time_range is None