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