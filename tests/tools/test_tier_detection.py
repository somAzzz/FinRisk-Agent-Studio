import pytest
from tools.tier_detection import detect_search_tier, is_direct_url

def test_simple_query_detects_ddgs():
    """fact-check query should route to ddgs."""
    assert detect_search_tier("Is Apple a good stock?") == "ddgs"
    assert detect_search_tier("What is Apple's stock ticker?") == "ddgs"
    assert detect_search_tier("Apple official website") == "ddgs"
    assert detect_search_tier("What is NVDA?") == "ddgs"

def test_deep_search_detects_tavily():
    """Analysis query should route to tavily."""
    assert detect_search_tier("Apple Q1 2026 earnings analysis") == "tavily"
    assert detect_search_tier("Latest news about Tesla") == "tavily"
    assert detect_search_tier("NVDA vs AMD comparison") == "tavily"
    assert detect_search_tier("Tesla stock trend analysis") == "tavily"

def test_financial_entity_multi_routes_to_tavily():
    """Financial entity + multi → tavily."""
    assert detect_search_tier("Compare all tech stocks") == "tavily"
    assert detect_search_tier("Multi stock analysis") == "tavily"

def test_url_detection():
    """URL input should be detected."""
    assert is_direct_url("https://seekingalpha.com/article/123") == True
    assert is_direct_url("http://reuters.com/news") == True
    assert is_direct_url("Apple stock analysis") == False