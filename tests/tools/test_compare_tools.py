from scripts.compare_tools.caller import ProjectCaller
from scripts.compare_tools.models import (
    BatchReport,
    ComparisonResult,
    ToolResult,
    WebFetchTestCase,
    WebSearchTestCase,
)


def test_project_caller_web_search():
    caller = ProjectCaller()
    result = caller.call_web_search("Tesla stock analysis")
    assert result.success is True
    assert len(result.output) > 0

def test_project_caller_web_fetch():
    caller = ProjectCaller()
    result = caller.call_web_fetch("https://en.wikipedia.org")
    assert result.success is True

def test_ansi_cleanup():
    """Test that ANSI codes are stripped from output."""
    from scripts.compare_tools.caller import _strip_ansi
    dirty = "\x1b[32mGreen\x1b[0m text"
    clean = _strip_ansi(dirty)
    assert clean == "Green text"
    assert "\x1b" not in clean

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

def test_keyword_coverage():
    from scripts.compare_tools.comparator import Comparator
    comp = Comparator()
    output = "Tesla reported revenue of $10B this quarter"
    keywords = ["revenue", "Tesla", "billion"]
    coverage = comp._calc_keyword_coverage(output, keywords)
    assert coverage == 2 / 3  # 2 out of 3 keywords found

def test_rag_score():
    from scripts.compare_tools.comparator import Comparator
    comp = Comparator()
    # Markdown content
    md_output = "# Title\n\nParagraph one.\n\nParagraph two."
    score = comp._calc_rag_score(md_output)
    assert score > 0.5  # Has headings and paragraphs

    # Plain text
    plain_output = "Just some plain text without any markdown."
    plain_score = comp._calc_rag_score(plain_output)
    assert plain_score < score
