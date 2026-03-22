# Tool Comparison Skill Design

## Overview

Create an independent comparison test tool `scripts/compare_tools.py` that supports batch and end-to-end comparison of project tools vs Claude Code tools output quality.

## Core Modules

### 1. Running Modes

| Mode | Command | Description |
|------|---------|-------------|
| Single query | `--tool <name> --query <text>` or `--tool <name> --url <url>` | Test single query or URL |
| Batch file | `--batch <file.json>` | Read multiple test cases from JSON file |
| Interactive | `--repl` | REPL mode, real-time input testing |

Where `<name>` is `web_search` or `web_fetch`.

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

**Validation:** On first run, verify `claude` command supports `--output-format stream-json`. If not supported, fall back to parsing plain text output and log a warning.

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
| Completeness | Key info coverage | `expected_keywords` hit rate in output |
| Accuracy | Accuracy score | Cosine similarity between output and `expected_content` embeddings |
| Speed | Response time | Average across runs (exclude cold start) |
| Error rate | Failure rate | failures / total |
| RAG friendliness | Structure score | Markdown-formatted lines / total lines, paragraph count, code block presence |
| Edge cases | Blacklist/truncation | Verify blacklisted domains are rejected; truncation at word boundary within 10% of limit |

**Note:** All metrics use test-case-level `expected_keywords` or `expected_content` fields defined in batch file.

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
│  Compare:                                       │
│  - web_search: each result entry               │
│  - web_fetch: each paragraph/text block         │
│  + score + issue detection                     │
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
python scripts/compare_tools.py --tool web_search --query "Apple Q4 2024 earnings"

# Single web_fetch comparison
python scripts/compare_tools.py --tool web_fetch --url "https://example.com/article"

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
    {"query": "Apple earnings Q4", "expected_keywords": ["revenue", "EPS"], "expected_content": "Apple Inc. reported quarterly earnings of $X.XX per share..."}
  ],
  "web_fetch": [
    {"url": "https://news.example.com/tech", "expected_keywords": ["AI", "growth"], "expected_content": "The article discusses..."}
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes (web_search) | Search query |
| `url` | string | Yes (web_fetch) | URL to fetch |
| `expected_keywords` | string[] | No | Keywords that should appear in output |
| `expected_content` | string | No | Reference content for accuracy comparison |

## Open Questions / Future Improvements

- [ ] Support calling Claude Code via MCP protocol if available
- [ ] Persist results to local database for historical comparison
- [ ] Add diff visualization in HTML report
- [ ] Support custom evaluation criteria per test case
