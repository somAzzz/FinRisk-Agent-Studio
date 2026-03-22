# Tool Comparison Skill Design

## Overview

Create an independent comparison test tool `scripts/compare_tools.py` that supports batch and end-to-end comparison of project tools vs Claude Code tools output quality.

## Core Modules

### 1. Running Modes

| Mode | Command | Description |
|------|---------|-------------|
| Single query | `--query <text>` or `--url <url>` | Test single query or URL |
| Batch file | `--batch <file.json>` | Read multiple test cases from JSON/YAML |
| Interactive | `--repl` | REPL mode, real-time input testing |

### 2. Tool Calling Layer

```
ToolCaller (abstract layer)
├── ProjectTools (call project web_search/web_fetch)
└── ClaudeCodeTools (via subprocess calling claude command)
```

**Claude Code invocation:** Uses `subprocess` to execute:
```bash
claude -m "web_search: {query}" --output-format stream-json
claude -m "web_fetch: {url}" --output-format stream-json
```

### 3. Report Generator

Generates dual-format reports:
- **Markdown** (`report_<timestamp>.md`) - Easy to read and version control
- **HTML** (`report_<timestamp>.html`) - Easy to share and visualize

**Report Structure:**
```
# Tool Comparison Report
## Summary (basic metric cards)
## Detailed Results
### Test Case 1: <query/url>
#### Project Tool Output
#### Claude Code Tool Output
#### Comparison & Analysis
## Issues Found
## Optimization Suggestions
```

### 4. Evaluation Metrics

| Dimension | Metric | Calculation |
|-----------|--------|-------------|
| Completeness | Key info coverage | Define key info points, count hits |
| Accuracy | Accuracy score | Compare with authoritative source |
| Speed | Response time | Average of multiple runs |
| Error rate | Failure rate | failures / total |
| RAG friendliness | Structure score | markdown rate, paragraph count |
| Edge cases | Blacklist/truncation | Specific test cases for validation |

## Data Flow

```
User Input (query/url/batch file)
    ↓
TestCase Creator
    ↓
┌─────────────────────────────────────┐
│  ProjectTools          ClaudeCodeTools │
│  (sync call)            (subprocess)      │
└─────────────────────────────────────┘
    ↓                    ↓
┌─────────────────────────────────────┐
│           Result Comparator           │
│  (item-by-item compare + score + issue detection)          │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│         Report Generator             │
│  (Markdown + HTML)                   │
└─────────────────────────────────────┘
```

## File Structure

```
scripts/
  compare_tools.py          # Main entry script
  compare_tools/
    __init__.py
    caller.py               # Tool calling layer (Project + ClaudeCode)
    comparator.py            # Result comparison logic
    reporter.py              # Report generator
    models.py                # Data models (TestCase, TestResult etc.)
    cli.py                   # CLI argument parsing

docs/superpowers/specs/
  2026-03-22-tool-comparison-design.md  # This design doc
```

## Example Usage

```bash
# Single web_search comparison
python scripts/compare_tools.py --tool web-search --query "Apple Q4 2024 earnings"

# Single web_fetch comparison
python scripts/compare_tools.py --tool web-fetch --url "https://example.com/article"

# Batch testing
python scripts/compare_tools.py --batch test_cases.json

# Interactive REPL
python scripts/compare_tools.py --repl
```

## Batch File Format

```json
{
  "web_search": [
    {"query": "Tesla stock analysis", "expected_keywords": ["revenue", "EV"]},
    {"query": "Apple earnings Q4"}
  ],
  "web_fetch": [
    {"url": "https://news.example.com/tech", "expected_keywords": ["AI", "growth"]}
  ]
}
```

## Open Questions / Future Improvements

- [ ] Support calling Claude Code via MCP protocol if available
- [ ] Persist results to local database for historical comparison
- [ ] Add diff visualization in HTML report
- [ ] Support custom evaluation criteria per test case
