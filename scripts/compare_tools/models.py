"""Data models for tool comparison."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class WebSearchTestCase:
    """Test case for web_search tool."""
    query: str
    expected_keywords: list[str] = field(default_factory=list)
    expected_content: str | None = None

@dataclass
class WebFetchTestCase:
    """Test case for web_fetch tool."""
    url: str
    expected_keywords: list[str] = field(default_factory=list)
    expected_content: str | None = None

@dataclass
class ToolResult:
    """Result from a tool execution."""
    tool_name: Literal["project", "claude_code"]
    output: str
    duration_seconds: float
    success: bool
    error: str | None = None

@dataclass
class ComparisonResult:
    """Comparison result between two tool outputs."""
    test_case: WebSearchTestCase | WebFetchTestCase
    project_result: ToolResult
    claude_code_result: ToolResult
    keyword_coverage_project: float
    keyword_coverage_claude: float
    # LLM judge fields
    llm_judge_score_project: float | None = None
    llm_judge_score_claude: float | None = None
    llm_judge_explanation: str | None = None
    # RAG metrics
    rag_score_project: float = 0.0
    rag_score_claude: float = 0.0

@dataclass
class BatchReport:
    """Full batch comparison report."""
    results: list[ComparisonResult]
    summary: dict
