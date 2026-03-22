from scripts.compare_tools.models import WebSearchTestCase, WebFetchTestCase, ToolResult, ComparisonResult, BatchReport

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

def test_comparison_result():
    tc = WebSearchTestCase(query="test")
    project_result = ToolResult(
        tool_name="project",
        output="project output",
        duration_seconds=1.0,
        success=True
    )
    claude_result = ToolResult(
        tool_name="claude_code",
        output="claude output",
        duration_seconds=2.0,
        success=True
    )
    comparison = ComparisonResult(
        test_case=tc,
        project_result=project_result,
        claude_code_result=claude_result,
        keyword_coverage_project=0.8,
        keyword_coverage_claude=0.9,
    )
    assert comparison.keyword_coverage_project == 0.8
    assert comparison.keyword_coverage_claude == 0.9

def test_batch_report():
    report = BatchReport(
        results=[],
        summary={"total": 0}
    )
    assert report.summary["total"] == 0
