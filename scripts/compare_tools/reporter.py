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