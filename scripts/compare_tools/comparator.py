"""Comparison logic for tool outputs."""

import os

from openai import OpenAI

from scripts.compare_tools.models import (
    ComparisonResult,
    ToolResult,
    WebFetchTestCase,
    WebSearchTestCase,
)


class Comparator:
    """Compares outputs from two tool callers."""

    def compare(
        self,
        test_case: WebSearchTestCase | WebFetchTestCase,
        project_result: ToolResult,
        claude_code_result: ToolResult,
    ) -> ComparisonResult:
        """Compare two tool results and compute metrics."""
        # Keyword coverage
        output_project = project_result.output
        output_claude = claude_code_result.output

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

    def _calc_keyword_coverage(self, output: str, keywords: list[str]) -> float:
        """Calculate what fraction of keywords appear in output."""
        if not keywords:
            return 1.0

        output_lower = output.lower()
        hits = sum(1 for kw in keywords if kw.lower() in output_lower)
        return hits / len(keywords)

    def _calc_rag_score(self, output: str) -> float:
        """Calculate RAG-friendliness score 0-1.

        Based on:
        - Markdown formatting (headings, lists, code blocks)
        - Paragraph count
        - Presence of code blocks
        """
        if not output:
            return 0.0

        lines = output.split('\n')

        # Heading detection (very important for RAG)
        heading_lines = [l for l in lines if l.strip().startswith(('#', '##', '###'))]
        heading_count = len(heading_lines)
        heading_score = min(heading_count * 0.45, 0.75)  # Each heading adds up to 0.75

        # List items
        list_markers = ['- ', '* ', '1. ', '2. ', '3. ', '4. ', '5. ']
        list_lines = sum(1 for line in lines if any(line.strip().startswith(m) for m in list_markers))
        list_score = min(list_lines * 0.1, 0.2)  # Each list item adds up to 0.2

        # Paragraph count (non-empty lines separated by blank lines)
        paragraphs = [p.strip() for p in output.split('\n\n') if p.strip()]
        para_count = len(paragraphs)
        para_score = min(para_count / 5, 1.0) * 0.15  # Cap at 5 paragraphs, weighted 0.15

        # Code block detection
        has_code = '```' in output
        code_score = 0.1 if has_code else 0.0

        # Weighted sum
        return heading_score + list_score + para_score + code_score

    def llm_judge(
        self,
        query: str,
        output_a: str,
        output_b: str,
        model: str = "Qwen/Qwen3.5-35B-A3B",
    ) -> tuple[float, float, str]:
        """Use LLM to judge which output is better.

        Returns (score_a, score_b, explanation).
        """
        # Check if OPENAI_API_KEY or VLLM_BASE_URL is set
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