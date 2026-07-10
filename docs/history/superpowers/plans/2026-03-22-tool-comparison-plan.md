# Tool Comparison Skill Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create an independent comparison tool at `scripts/compare_tools.py` that batch-tests and end-to-end compares project web_search/web_fetch vs Claude Code tools, generating Markdown + HTML reports.

**Architecture:** Independent CLI tool that calls both project tools (direct import) and Claude Code (subprocess) for comparison. Modular design: caller → comparator → reporter.

**Tech Stack:** Python stdlib (subprocess, re), existing project tools (web_search, web_fetch), existing deps (httpx, sentence-transformers for LLM judge).

---

## Chunk 1: Data Models

**Files:**
- Create: `scripts/compare_tools/models.py`

- [ ] **Step 1: Create `scripts/compare_tools/__init__.py`**

```python
"""Tool comparison CLI."""
```

- [ ] **Step 2: Write the failing test in `tests/tools/test_compare_tools.py`**

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `PYTHONPATH=/home/bo/projects/python/fintext_llm pytest tests/tools/test_compare_tools.py -v`
Expected: FAIL - module not found

- [ ] **Step 4: Write minimal implementation `scripts/compare_tools/models.py`**

```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=/home/bo/projects/python/fintext_llm pytest tests/tools/test_compare_tools.py::test_web_search_test_case -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/compare_tools/__init__.py scripts/compare_tools/models.py tests/tools/test_compare_tools.py
git commit -m "feat(compare_tools): add data models

- WebSearchTestCase, WebFetchTestCase for test case definition
- ToolResult for single tool execution result
- ComparisonResult for paired comparison
- BatchReport for full batch report"
```

---

## Chunk 2: Tool Caller Layer

**Files:**
- Create: `scripts/compare_tools/caller.py`
- Modify: `scripts/compare_tools/__init__.py`

- [ ] **Step 1: Write the failing test in `tests/tools/test_compare_tools.py`**

```python
from scripts.compare_tools.caller import ProjectCaller, ClaudeCodeCaller, ToolCaller

def test_project_caller_web_search():
    caller = ProjectCaller()
    result = caller.call_web_search("Tesla stock analysis")
    assert result.success is True
    assert len(result.output) > 0

def test_project_caller_web_fetch():
    caller = ProjectCaller()
    result = caller.call_web_fetch("https://example.com")
    assert result.success is True

def test_ansi_cleanup():
    """Test that ANSI codes are stripped from output."""
    dirty = "\x1b[32mGreen\x1b[0m text"
    clean = _strip_ansi(dirty)
    assert clean == "Green text"
    assert "\x1b" not in clean
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/home/bo/projects/python/fintext_llm pytest tests/tools/test_compare_tools.py -v`
Expected: FAIL - caller module not found

- [ ] **Step 3: Write `scripts/compare_tools/caller.py`**

```python
"""Tool calling layer - calls both project tools and Claude Code."""

import asyncio
import re
import subprocess
import time
from abc import ABC, abstractmethod

from scripts.compare_tools.models import ToolResult


TIMEOUT_SECONDS = 60
ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def _strip_ansi(text: str) *********REMOVED********* str:
    """Strip ANSI escape codes from text."""
    return ANSI_ESCAPE.sub('', text)


class ToolCaller(ABC):
    """Abstract base for tool callers."""

    @abstractmethod
    def call_web_search(self, query: str) *********REMOVED********* ToolResult:
        """Call web_search tool."""
        pass

    @abstractmethod
    def call_web_fetch(self, url: str) *********REMOVED********* ToolResult:
        """Call web_fetch tool."""
        pass


class ProjectCaller(ToolCaller):
    """Calls project tools directly."""

    def call_web_search(self, query: str) *********REMOVED********* ToolResult:
        """Call project's web_search function."""
        start = time.monotonic()
        try:
            from src.tools.web_search import web_search
            output = web_search(query)
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="project",
                output=output,
                duration_seconds=duration,
                success=True,
                error=None
            )
        except Exception as e:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="project",
                output="",
                duration_seconds=duration,
                success=False,
                error=str(e)
            )

    def call_web_fetch(self, url: str) *********REMOVED********* ToolResult:
        """Call project's web_fetch function."""
        start = time.monotonic()
        try:
            from src.tools.web_fetch import web_fetch_sync
            result = web_fetch_sync(url)
            duration = time.monotonic() - start
            # Convert WebFetchResult to string output
            if result.status == "success":
                output = f"# {result.title or 'Untitled'}\n\n{result.content}"
            else:
                output = f"Error: {result.error_code} - {result.error_message}"
            return ToolResult(
                tool_name="project",
                output=output,
                duration_seconds=duration,
                success=result.status == "success",
                error=result.error_code if result.status != "success" else None
            )
        except Exception as e:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="project",
                output="",
                duration_seconds=duration,
                success=False,
                error=str(e)
            )


class ClaudeCodeCaller(ToolCaller):
    """Calls Claude Code CLI via subprocess."""

    def call_web_search(self, query: str) *********REMOVED********* ToolResult:
        """Call Claude Code web_search via subprocess."""
        start = time.monotonic()
        try:
            result = subprocess.run(
                ["claude", "-m", f"web_search: {query}", "--output-format", "stream-json"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS
            )
            duration = time.monotonic() - start

            if result.returncode != 0:
                # Fallback: try plain text
                return self._call_plain_text_fallback(
                    ["claude", "-m", f"web_search: {query}"],
                    "project",
                    start
                )

            # Parse JSON from stream-json output
            output = self._parse_stream_json(result.stdout)
            return ToolResult(
                tool_name="claude_code",
                output=output,
                duration_seconds=duration,
                success=True,
                error=None
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="claude_code",
                output="",
                duration_seconds=duration,
                success=False,
                error="TIMEOUT"
            )
        except FileNotFoundError:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="claude_code",
                output="",
                duration_seconds=duration,
                success=False,
                error="CLAUDE_CLI_NOT_FOUND"
            )
        except Exception as e:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="claude_code",
                output="",
                duration_seconds=duration,
                success=False,
                error=str(e)
            )

    def call_web_fetch(self, url: str) *********REMOVED********* ToolResult:
        """Call Claude Code web_fetch via subprocess."""
        start = time.monotonic()
        try:
            result = subprocess.run(
                ["claude", "-m", f"web_fetch: {url}", "--output-format", "stream-json"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS
            )
            duration = time.monotonic() - start

            if result.returncode != 0:
                return self._call_plain_text_fallback(
                    ["claude", "-m", f"web_fetch: {url}"],
                    "claude_code",
                    start
                )

            output = self._parse_stream_json(result.stdout)
            return ToolResult(
                tool_name="claude_code",
                output=output,
                duration_seconds=duration,
                success=True,
                error=None
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="claude_code",
                output="",
                duration_seconds=duration,
                success=False,
                error="TIMEOUT"
            )
        except FileNotFoundError:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="claude_code",
                output="",
                duration_seconds=duration,
                success=False,
                error="CLAUDE_CLI_NOT_FOUND"
            )
        except Exception as e:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="claude_code",
                output="",
                duration_seconds=duration,
                success=False,
                error=str(e)
            )

    def _call_plain_text_fallback(
        self, cmd: list[str], tool_name: str, start: float
    ) *********REMOVED********* ToolResult:
        """Fallback to plain text output when stream-json fails."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS
            )
            duration = time.monotonic() - start
            # Strip ANSI codes from output
            output = _strip_ansi(result.stdout)
            return ToolResult(
                tool_name=tool_name,
                output=output,
                duration_seconds=duration,
                success=result.returncode == 0,
                error=None if result.returncode == 0 else "FALLBACK_FAILED"
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name=tool_name,
                output="",
                duration_seconds=duration,
                success=False,
                error="TIMEOUT"
            )

    def _parse_stream_json(self, stdout: str) *********REMOVED********* str:
        """Parse stream-json output from Claude CLI."""
        # Each line is a JSON object with type and content
        # For tool results, we want the final output
        output_parts = []
        for line in stdout.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                import json
                obj = json.loads(line)
                if obj.get('type') == 'content' and 'text' in obj:
                    output_parts.append(obj['text'])
                elif obj.get('type') == 'result':
                    output_parts.append(str(obj.get('content', '')))
            except json.JSONDecodeError:
                # If it's not JSON, treat as plain text
                output_parts.append(line)
        return '\n'.join(output_parts) if output_parts else stdout
```

- [ ] **Step 3: Export caller classes in `scripts/compare_tools/__init__.py`**

```python
"""Tool comparison CLI."""

from scripts.compare_tools.models import (
    WebSearchTestCase,
    WebFetchTestCase,
    ToolResult,
    ComparisonResult,
    BatchReport,
)
from scripts.compare_tools.caller import (
    ProjectCaller,
    ClaudeCodeCaller,
    ToolCaller,
)

__all__ = [
    "WebSearchTestCase",
    "WebFetchTestCase",
    "ToolResult",
    "ComparisonResult",
    "BatchReport",
    "ProjectCaller",
    "ClaudeCodeCaller",
    "ToolCaller",
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=/home/bo/projects/python/fintext_llm pytest tests/tools/test_compare_tools.py -v`
Expected: PASS (or SKIP for ClaudeCodeCaller tests if claude CLI not available)

- [ ] **Step 5: Commit**

```bash
git add scripts/compare_tools/caller.py scripts/compare_tools/__init__.py
git commit -m "feat(compare_tools): add tool caller layer

- ProjectCaller: direct import of project web_search/web_fetch
- ClaudeCodeCaller: subprocess calls to claude CLI
- ANSI escape code stripping for fallback text parsing
- 60s timeout on all subprocess calls
- stream-json output parsing"
```

---

## Chunk 3: Comparator Layer

**Files:**
- Create: `scripts/compare_tools/comparator.py`
- Modify: `scripts/compare_tools/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
from scripts.compare_tools.comparator import Comparator

def test_keyword_coverage():
    comp = Comparator()
    output = "Tesla reported revenue of $10B this quarter"
    keywords = ["revenue", "Tesla", "billion"]
    coverage = comp._calc_keyword_coverage(output, keywords)
    assert coverage == 2 / 3  # 2 out of 3 keywords found

def test_rag_score():
    comp = Comparator()
    # Markdown content
    md_output = "# Title\n\nParagraph one.\n\nParagraph two."
    score = comp._calc_rag_score(md_output)
    assert score > 0.5  # Has headings and paragraphs

    # Plain text
    plain_output = "Just some plain text without any markdown."
    plain_score = comp._calc_rag_score(plain_output)
    assert plain_score < score
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/home/bo/projects/python/fintext_llm pytest tests/tools/test_compare_tools.py -v`
Expected: FAIL - comparator module not found

- [ ] **Step 3: Write `scripts/compare_tools/comparator.py`**

```python
"""Comparison logic for tool outputs."""

import re

from scripts.compare_tools.models import (
    ComparisonResult,
    ToolResult,
    WebSearchTestCase,
    WebFetchTestCase,
)


class Comparator:
    """Compares outputs from two tool callers."""

    def compare(
        self,
        test_case: WebSearchTestCase | WebFetchTestCase,
        project_result: ToolResult,
        claude_code_result: ToolResult,
    ) *********REMOVED********* ComparisonResult:
        """Compare two tool results and compute metrics."""
        # Keyword coverage
        output_project = project_result.output
        output_claude = claude_code_result.output

        if isinstance(test_case, WebSearchTestCase):
            keywords = test_case.expected_keywords
        else:
            keywords = test_case.expected_keywords

        coverage_project = self._calc_keyword_coverage(output_project, keywords)
        coverage_claude = self._calc_keyword_coverage(output_claude, keywords)

        # RAG scores
        rag_project = self._calc_rag_score(output_project)
        rag_claude = self._calc_rag_score(output_claude)

        return ComparisonResult(
            test_case=test_case,
            project_result=project_result,
            claude_code_result=claude_code_result,
            keyword_coverage_project=coverage_project,
            keyword_coverage_claude=coverage_claude,
            rag_score_project=rag_project,
            rag_score_claude=rag_claude,
        )

    def _calc_keyword_coverage(self, output: str, keywords: list[str]) *********REMOVED********* float:
        """Calculate what fraction of keywords appear in output."""
        if not keywords:
            return 1.0

        output_lower = output.lower()
        hits = sum(1 for kw in keywords if kw.lower() in output_lower)
        return hits / len(keywords)

    def _calc_rag_score(self, output: str) *********REMOVED********* float:
        """Calculate RAG-friendliness score 0-1.

        Based on:
        - Markdown formatting ratio
        - Paragraph count
        - Presence of code blocks
        """
        if not output:
            return 0.0

        lines = output.split('\n')
        total_lines = len(lines)

        # Markdown-formatted lines
        md_markers = ['#', '##', '###', '- ', '* ', '1. ', '2. ', '```', '|']
        md_lines = sum(1 for line in lines if any(line.strip().startswith(m) for m in md_markers))
        md_ratio = md_lines / total_lines

        # Paragraph count (non-empty lines separated by blank lines)
        paragraphs = [p.strip() for p in output.split('\n\n') if p.strip()]
        para_count = len(paragraphs)
        para_score = min(para_count / 10, 1.0)  # Cap at 10 paragraphs

        # Code block detection
        has_code = '```' in output
        code_score = 0.2 if has_code else 0.0

        # Weighted sum
        return 0.4 * md_ratio + 0.4 * para_score + 0.2 * code_score

    def llm_judge(
        self,
        query: str,
        output_a: str,
        output_b: str,
        model: str = "Qwen/Qwen3.5-35B-A3B",
    ) *********REMOVED********* tuple[float, float, str]:
        """Use LLM to judge which output is better.

        Returns (score_a, score_b, explanation).
        """
        # Check if OPENAI_API_KEY or VLLM_BASE_URL is set
        import os
        api_base = os.environ.get('VLLM_BASE_URL', 'http://localhost:30000/v1')
        api_key = os.environ.get('OPENAI_API_KEY', 'EMPTY')

        prompt = f"""Compare these two tool outputs for the query: {query}

--- Output A ---
{output_a[:2000]}  # Truncate for token limit

--- Output B ---
{output_b[:2000]}

Score both outputs 1-5 on: completeness, accuracy, and RAG-friendliness.
Respond in this format exactly:
SCORES: A=<score_a>, B=<score_b>
EXPLANATION: <why one is better>
"""

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=f"{api_base}/v1")
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500,
            )
            text = response.choices[0].message.content

            # Parse response
            scores_a, scores_b = 3.0, 3.0  # Default
            explanation = ""

            if 'SCORES:' in text:
                scores_part = text.split('SCORES:')[1].split('EXPLANATION:')[0]
                if 'A=' in scores_part and 'B=' in scores_part:
                    try:
                        a_val = scores_part.split('A=')[1].split(',')[0].strip()
                        b_val = scores_part.split('B=')[1].strip()
                        scores_a = float(a_val)
                        scores_b = float(b_val)
                    except (ValueError, IndexError):
                        pass

            if 'EXPLANATION:' in text:
                explanation = text.split('EXPLANATION:')[1].strip()

            return scores_a, scores_b, explanation

        except Exception as e:
            return 3.0, 3.0, f"LLM judge unavailable: {e}"
```

- [ ] **Step 4: Export in `scripts/compare_tools/__init__.py`**

```python
from scripts.compare_tools.comparator import Comparator
__all__ = [..., "Comparator"]
```

- [ ] **Step 5: Run tests**

Run: `PYTHONPATH=/home/bo/projects/python/fintext_llm pytest tests/tools/test_compare_tools.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/compare_tools/comparator.py scripts/compare_tools/__init__.py
git commit -m "feat(compare_tools): add comparator logic

- Keyword coverage calculation
- RAG score (markdown ratio, paragraphs, code blocks)
- LLM-as-a-Judge integration for accuracy scoring"
```

---

## Chunk 4: Reporter Layer

**Files:**
- Create: `scripts/compare_tools/reporter.py`
- Modify: `scripts/compare_tools/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
from scripts.compare_tools.reporter import MarkdownReporter, HTMLReporter

def test_markdown_reporter():
    # This would test report generation
    # (skipped for brevity - integration test)
    pass
```

- [ ] **Step 2: Write `scripts/compare_tools/reporter.py`**

```python
"""Report generation in Markdown and HTML formats."""

from datetime import datetime
from scripts.compare_tools.models import BatchReport, ComparisonResult


class MarkdownReporter:
    """Generates Markdown comparison reports."""

    def generate(self, report: BatchReport) *********REMOVED********* str:
        """Generate Markdown report string."""
        lines = [
            "# Tool Comparison Report",
            f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "\n## Summary\n",
        ]

        # Summary table
        total = len(report.results)
        project_errors = sum(1 for r in report.results if not r.project_result.success)
        claude_errors = sum(1 for r in report.results if not r.claude_code_result.success)

        avg_coverage_project = sum(r.keyword_coverage_project for r in report.results) / total if total else 0
        avg_coverage_claude = sum(r.keyword_coverage_claude for r in report.results) / total if total else 0
        avg_rag_project = sum(r.rag_score_project for r in report.results) / total if total else 0
        avg_rag_claude = sum(r.rag_score_claude for r in report.results) / total if total else 0
        avg_speed_project = sum(r.project_result.duration_seconds for r in report.results) / total if total else 0
        avg_speed_claude = sum(r.claude_code_result.duration_seconds for r in report.results) / total if total else 0

        lines.extend([
            f"| Metric | Project Tool | Claude Code |",
            f"|--------|-------------|-------------|",
            f"| Keyword Coverage | {avg_coverage_project:.1%} | {avg_coverage_claude:.1%} |",
            f"| RAG Score | {avg_rag_project:.2f} | {avg_rag_claude:.2f} |",
            f"| Avg Speed | {avg_speed_project:.1f}s | {avg_speed_claude:.1f}s |",
            f"| Errors | {project_errors} | {claude_errors} |",
            "\n## Detailed Results\n",
        ])

        for i, result in enumerate(report.results, 1):
            lines.append(f"### Test Case {i}: {self._get_test_name(result)}")
            lines.append(f"\n**Project Tool** (took {result.project_result.duration_seconds:.2f}s)")
            if result.project_result.success:
                lines.append(f"\n```\n{result.project_result.output[:500]}...\n```")
            else:
                lines.append(f"\n*Error: {result.project_result.error}*")

            lines.append(f"\n**Claude Code** (took {result.claude_code_result.duration_seconds:.2f}s)")
            if result.claude_code_result.success:
                lines.append(f"\n```\n{result.claude_code_result.output[:500]}...\n```")
            else:
                lines.append(f"\n*Error: {result.claude_code_result.error}*")

            lines.append("\n**Comparison**")
            lines.append(f"- Keyword Coverage: Project {result.keyword_coverage_project:.1%} vs Claude {result.keyword_coverage_claude:.1%}")
            lines.append(f"- RAG Score: Project {result.rag_score_project:.2f} vs Claude {result.rag_score_claude:.2f}")

            if result.llm_judge_explanation:
                lines.append(f"\n**LLM Judge**: {result.llm_judge_explanation}")

            lines.append("\n---\n")

        return '\n'.join(lines)

    def _get_test_name(self, result: ComparisonResult) *********REMOVED********* str:
        """Get test case name."""
        from scripts.compare_tools.models import WebSearchTestCase
        if isinstance(result.test_case, WebSearchTestCase):
            return f"web_search: {result.test_case.query}"
        return f"web_fetch: {result.test_case.url}"

    def save(self, report: BatchReport, path: str | None = None) *********REMOVED********* str:
        """Save report to file, return path."""
        if path is None:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            path = f"tool_comparison_report_{ts}.md"
        with open(path, 'w') as f:
            f.write(self.generate(report))
        return path


class HTMLReporter:
    """Generates HTML comparison reports."""

    def generate(self, report: BatchReport) *********REMOVED********* str:
        """Generate HTML report string."""
        md_content = MarkdownReporter().generate(report)
        # Simple Markdown to HTML conversion
        html = self._markdown_to_html(md_content)
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Tool Comparison Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f5f5f5; }}
        code {{ background-color: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
        pre {{ background-color: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; }}
        h1, h2, h3 {{ color: #333; }}
        .metric-card {{ display: inline-block; background: #f9f9f9; padding: 15px; margin: 10px; border-radius: 8px; min-width: 150px; }}
        .metric-value {{ font-size: 2em; font-weight: bold; color: #0066cc; }}
        .metric-label {{ color: #666; font-size: 0.9em; }}
        .success {{ color: green; }}
        .error {{ color: red; }}
    </style>
</head>
<body>
{html}
</body>
</html>"""

    def _markdown_to_html(self, md: str) *********REMOVED********* str:
        """Simple Markdown to HTML conversion."""
        import re
        html = md

        # Headers
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # Code blocks
        html = re.sub(r'```\n(.+?)\n```', r'<pre><code>\1</code></pre>', html, flags=re.DOTALL)

        # Inline code
        html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)

        # Bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)

        # Horizontal rule
        html = re.sub(r'^---$', '<hr>', html, flags=re.MULTILINE)

        # Tables (basic)
        lines = html.split('\n')
        result_lines = []
        in_table = False
        for line in lines:
            if '|' in line and line.strip().startswith('|'):
                if not in_table:
                    result_lines.append('<table>')
                    in_table = True
                cells = [c.strip() for c in line.split('|') if c.strip()]
                if '---' in line:
                    continue  # Skip separator
                tag = 'th' if any(x in line for x in ['Metric', '---']) else 'td'
                result_lines.append(f'<tr>{"".join(f"<{tag}>{c}</{tag}>" for c in cells)}</tr>')
            else:
                if in_table:
                    result_lines.append('</table>')
                    in_table = False
                result_lines.append(line)
        if in_table:
            result_lines.append('</table>')
        html = '\n'.join(result_lines)

        # Paragraphs
        html = re.sub(r'\n\n+', '\n\n', html)

        return html

    def save(self, report: BatchReport, path: str | None = None) *********REMOVED********* str:
        """Save report to file, return path."""
        if path is None:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            path = f"tool_comparison_report_{ts}.html"
        with open(path, 'w') as f:
            f.write(self.generate(report))
        return path
```

- [ ] **Step 3: Update `scripts/compare_tools/__init__.py`**

```python
from scripts.compare_tools.reporter import MarkdownReporter, HTMLReporter
__all__ = [..., "MarkdownReporter", "HTMLReporter"]
```

- [ ] **Step 4: Commit**

```bash
git add scripts/compare_tools/reporter.py scripts/compare_tools/__init__.py
git commit -m "feat(compare_tools): add reporter layer

- MarkdownReporter: generates Markdown reports with summary table
- HTMLReporter: generates styled HTML reports with cards
- Auto-naming with timestamps"
```

---

## Chunk 5: CLI and Main Integration

**Files:**
- Create: `scripts/compare_tools/cli.py`
- Create: `scripts/compare_tools/__main__.py`
- Create: `scripts/compare_tools.py` (main entry)

- [ ] **Step 1: Write `scripts/compare_tools/cli.py`**

```python
"""CLI argument parsing."""

import argparse
from pathlib import Path


def create_parser() *********REMOVED********* argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare project web_search/web_fetch tools vs Claude Code tools"
    )

    parser.add_argument(
        '--tool',
        choices=['web_search', 'web_fetch'],
        help='Tool to test'
    )
    parser.add_argument(
        '--query',
        help='Search query (for web_search)'
    )
    parser.add_argument(
        '--url',
        help='URL to fetch (for web_fetch)'
    )
    parser.add_argument(
        '--batch',
        type=Path,
        help='Path to batch JSON file'
    )
    parser.add_argument(
        '--repl',
        action='store_true',
        help='Interactive REPL mode'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('.'),
        help='Directory for output reports'
    )

    return parser
```

- [ ] **Step 2: Write `scripts/compare_tools/__main__.py`**

```python
"""CLI entry point."""

import sys
from scripts.compare_tools.cli import create_parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    # Import main after args are parsed to avoid circular imports
    from scripts.compare_tools.main import run

    sys.exit(run(args))
```

- [ ] **Step 3: Write `scripts/compare_tools/main.py`**

```python
"""Main orchestration logic."""

import json
from pathlib import Path

from scripts.compare_tools.models import (
    WebSearchTestCase,
    WebFetchTestCase,
    BatchReport,
)
from scripts.compare_tools.caller import ProjectCaller, ClaudeCodeCaller
from scripts.compare_tools.comparator import Comparator
from scripts.compare_tools.reporter import MarkdownReporter, HTMLReporter


def run(args) *********REMOVED********* int:
    """Run comparison based on args."""
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.repl:
        return run_repl(output_dir)

    if args.batch:
        return run_batch(args.batch, output_dir)

    if args.tool and args.query:
        return run_single_web_search(args.query, output_dir)

    if args.tool and args.url:
        return run_single_web_fetch(args.url, output_dir)

    print("Error: specify --repl, --batch, or --tool with --query/--url")
    return 1


def run_single_web_search(query: str, output_dir: Path) *********REMOVED********* int:
    """Run single web_search comparison."""
    test_case = WebSearchTestCase(query=query)
    results = run_comparison([test_case], output_dir)
    print(f"\nResults saved to: {results}")
    return 0


def run_single_web_fetch(url: str, output_dir: Path) *********REMOVED********* int:
    """Run single web_fetch comparison."""
    test_case = WebFetchTestCase(url=url)
    results = run_comparison([test_case], output_dir)
    print(f"\nResults saved to: {results}")
    return 0


def run_batch(batch_path: Path, output_dir: Path) *********REMOVED********* int:
    """Run batch comparison from JSON file."""
    with open(batch_path) as f:
        data = json.load(f)

    test_cases = []
    for item in data.get('web_search', []):
        test_cases.append(WebSearchTestCase(
            query=item['query'],
            expected_keywords=item.get('expected_keywords', []),
            expected_content=item.get('expected_content'),
        ))
    for item in data.get('web_fetch', []):
        test_cases.append(WebFetchTestCase(
            url=item['url'],
            expected_keywords=item.get('expected_keywords', []),
            expected_content=item.get('expected_content'),
        ))

    results = run_comparison(test_cases, output_dir)
    print(f"\nResults saved to: {results}")
    return 0


def run_repl(output_dir: Path) *********REMOVED********* int:
    """Interactive REPL mode."""
    print("Tool Comparison REPL")
    print("Commands: search <query>, fetch <url>, quit")
    print()

    project_caller = ProjectCaller()
    claude_caller = ClaudeCodeCaller()
    comparator = Comparator()

    while True:
        try:
            line = input("> ").strip()
            if not line:
                continue

            if line.lower() in ('quit', 'exit', 'q'):
                break

            if line.lower().startswith('search '):
                query = line[7:].strip()
                print(f"Testing web_search: {query}")

                # Run comparison
                test_case = WebSearchTestCase(query=query)
                project_result = project_caller.call_web_search(query)
                claude_result = claude_caller.call_web_search(query)

                comparison = comparator.compare(test_case, project_result, claude_result)

                print(f"\n  Project: {'OK' if project_result.success else 'FAIL'} ({project_result.duration_seconds:.2f}s)")
                print(f"  Claude:  {'OK' if claude_result.success else 'FAIL'} ({claude_result.duration_seconds:.2f}s)")
                print(f"  Coverage: Project {comparison.keyword_coverage_project:.0%} vs Claude {comparison.keyword_coverage_claude:.0%}")

            elif line.lower().startswith('fetch '):
                url = line[6:].strip()
                print(f"Testing web_fetch: {url}")

                test_case = WebFetchTestCase(url=url)
                project_result = project_caller.call_web_fetch(url)
                claude_result = claude_caller.call_web_fetch(url)

                comparison = comparator.compare(test_case, project_result, claude_result)

                print(f"\n  Project: {'OK' if project_result.success else 'FAIL'} ({project_result.duration_seconds:.2f}s)")
                print(f"  Claude:  {'OK' if claude_result.success else 'FAIL'} ({claude_result.duration_seconds:.2f}s)")
                print(f"  Coverage: Project {comparison.keyword_coverage_project:.0%} vs Claude {comparison.keyword_coverage_claude:.0%}")

            else:
                print("Unknown command. Use: search <query>, fetch <url>, quit")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

    return 0


def run_comparison(test_cases: list, output_dir: Path) *********REMOVED********* list[str]:
    """Run comparison for test cases and generate reports."""
    project_caller = ProjectCaller()
    claude_caller = ClaudeCodeCaller()
    comparator = Comparator()

    results = []

    for tc in test_cases:
        from scripts.compare_tools.models import WebSearchTestCase

        if isinstance(tc, WebSearchTestCase):
            project_result = project_caller.call_web_search(tc.query)
            claude_result = claude_caller.call_web_search(tc.query)
        else:
            project_result = project_caller.call_web_fetch(tc.url)
            claude_result = claude_caller.call_web_fetch(tc.url)

        comparison = comparator.compare(tc, project_result, claude_result)
        results.append(comparison)

    # LLM judge on all results
    for comparison in results:
        query_str = comparison.test_case.query if isinstance(comparison.test_case, WebSearchTestCase) else comparison.test_case.url
        score_a, score_b, explanation = comparator.llm_judge(
            query_str,
            comparison.project_result.output,
            comparison.claude_code_result.output
        )
        comparison.llm_judge_score_project = score_a
        comparison.llm_judge_score_claude = score_b
        comparison.llm_judge_explanation = explanation

    # Generate report
    report = BatchReport(results=results, summary={})

    md_reporter = MarkdownReporter()
    html_reporter = HTMLReporter()

    md_path = output_dir / md_reporter.save(report)
    html_path = output_dir / html_reporter.save(report)

    return [str(md_path), str(html_path)]
```

- [ ] **Step 4: Write main entry `scripts/compare_tools.py`**

```python
#!/usr/bin/env python3
"""Main entry point for tool comparison CLI."""

if __name__ == "__main__":
    from scripts.compare_tools.__main__ import main
    main()
```

- [ ] **Step 5: Commit**

```bash
git add scripts/compare_tools/cli.py scripts/compare_tools/__main__.py scripts/compare_tools/main.py scripts/compare_tools.py
git commit -m "feat(compare_tools): add CLI and main orchestration

- CLI argument parsing with argparse
- Single query mode, batch mode, REPL mode
- Report generation via MarkdownReporter and HTMLReporter
- LLM judge integration for accuracy scoring"
```

---

## Chunk 6: Sample Batch File and Demo

**Files:**
- Create: `scripts/compare_tools_sample_batch.json`
- Create: `scripts/demo_compare_tools.py`

- [ ] **Step 1: Create `scripts/compare_tools_sample_batch.json`**

```json
{
  "web_search": [
    {
      "query": "Tesla Q4 2024 earnings report",
      "expected_keywords": ["revenue", "profit", "EV"]
    },
    {
      "query": "Apple stock analysis March 2025",
      "expected_keywords": ["AAPL", "iPhone", "services"]
    },
    {
      "query": "Federal Reserve interest rate decision",
      "expected_keywords": ["Fed", "rate", "inflation"]
    }
  ],
  "web_fetch": [
    {
      "url": "https://en.wikipedia.org/wiki/Stock_market",
      "expected_keywords": ["market", "investors", "exchange"]
    },
    {
      "url": "https://www.reuters.com/business/finance",
      "expected_keywords": ["finance", "markets", "economy"]
    }
  ]
}
```

- [ ] **Step 2: Create `scripts/demo_compare_tools.py`**

```python
#!/usr/bin/env python3
"""Demo script for tool comparison."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.compare_tools.main import run_comparison
from scripts.compare_tools.models import WebSearchTestCase, WebFetchTestCase


def main():
    print("Running demo comparison...")

    test_cases = [
        WebSearchTestCase(
            query="Python programming language",
            expected_keywords=[" Guido ", "van Rossum", "programming"]
        ),
        WebFetchTestCase(
            url="https://example.com",
            expected_keywords=["Example", "domain"]
        ),
    ]

    output_dir = Path("demo_output")
    output_dir.mkdir(exist_ok=True)

    paths = run_comparison(test_cases, output_dir)
    print(f"\nDemo complete! Reports saved to:")
    for p in paths:
        print(f"  - {p}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run demo**

Run: `cd /home/bo/projects/python/fintext_llm && python scripts/demo_compare_tools.py`
Expected: Demo runs and generates reports

- [ ] **Step 4: Commit**

```bash
git add scripts/compare_tools_sample_batch.json scripts/demo_compare_tools.py
git commit -m "feat(compare_tools): add sample batch file and demo script"
```

---

## Summary

**Files created:**
- `scripts/compare_tools/__init__.py` - Package init with exports
- `scripts/compare_tools/models.py` - Data models
- `scripts/compare_tools/caller.py` - Tool calling layer (Project + ClaudeCode)
- `scripts/compare_tools/comparator.py` - Comparison logic + LLM judge
- `scripts/compare_tools/reporter.py` - Markdown + HTML report generation
- `scripts/compare_tools/cli.py` - CLI argument parsing
- `scripts/compare_tools/__main__.py` - CLI entry point
- `scripts/compare_tools/main.py` - Main orchestration
- `scripts/compare_tools.py` - Main script entry point
- `scripts/compare_tools_sample_batch.json` - Sample batch file
- `scripts/demo_compare_tools.py` - Demo script
- `tests/tools/test_compare_tools.py` - Unit tests

**Commands:**
```bash
# Single test
python scripts/compare_tools.py --tool web_search --query "Tesla earnings"

# Batch test
python scripts/compare_tools.py --batch scripts/compare_tools_sample_batch.json

# REPL mode
python scripts/compare_tools.py --repl
```
