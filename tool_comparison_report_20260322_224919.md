# Tool Comparison Report

Generated: 2026-03-22 22:49:19

## Summary

| Metric | Project Tool | Claude Code |
|--------|-------------|-------------|
| Keyword Coverage | 66.7% | 0.0% |
| RAG Score | 0.61 | 0.00 |
| Avg Speed | 1.6s | 0.4s |
| Errors | 0 | 2 |

## Detailed Results

### Test Case 1: web_search: Python programming language

**Project Tool** (took 1.93s)

```
{"retrieved_at": "2026-03-22T21:49:17Z", "query_used": "Python programming language", "time_range_applied": null, "results": [{"title": "Python (programming language)", "url": "https://en.wikipedia.org/wiki/Python_(programming_language)", "published_at": null, "body": "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically type-checked and garbage-collected. It supports multipl...
```

**Claude Code** (took 0.38s)

*Error: FALLBACK_FAILED*

**Comparison**
- Keyword Coverage: Project 33.3% vs Claude 0.0%
- RAG Score: Project 0.03 vs Claude 0.00

**LLM Judge**: LLM judge unavailable: Error code: 404 - {'detail': 'Not Found'}

---

### Test Case 2: web_fetch: https://en.wikipedia.org/wiki/Python_(programming_language)

**Project Tool** (took 1.26s)

```
# Python (programming language) - Wikipedia

# Python (programming language)


| This article is part of
|

[Python]

**Python** is a [high-level](/wiki/High-level_programming_language), [general-purpose programming language](/wiki/General-purpose_programming_language). Its design philosophy emphasizes [code readability](/wiki/Code_readability) with the use of [significant indentation](/wiki/Significant_indentation). [38] Python is

[dynamically type-checked](/wiki/Type_system#DYNAMIC)and

[garb...
```

**Claude Code** (took 0.38s)

*Error: FALLBACK_FAILED*

**Comparison**
- Keyword Coverage: Project 100.0% vs Claude 0.0%
- RAG Score: Project 1.20 vs Claude 0.00

**LLM Judge**: LLM judge unavailable: Error code: 404 - {'detail': 'Not Found'}

---
