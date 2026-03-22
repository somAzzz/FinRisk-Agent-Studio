from scripts.compare_tools.models import WebSearchTestCase, WebFetchTestCase, ToolResult

def test_web_search_test_case():
    tc = WebSearchTestCase(
        query="Tesla earnings",
        expected_keywords=["revenue", "EV"]
    )
    assert tc.query == "Tesla earnings"
    assert "revenue" in tc.expected_keywords

def test_web_fetch_test_case():
    tc = WebFetchTestCase(
        url="https://example.com",
        expected_keywords=["AI"]
    )
    assert tc.url == "https://example.com"

def test_tool_result():
    result = ToolResult(
        tool_name="project",
        output="Test output",
        duration_seconds=1.5,
        success=True,
        error=None
    )
    assert result.success is True
    assert result.duration_seconds == 1.5
