# 08 - Testing 与 Acceptance

## Unit Tests

新增：

```text
tests/memory/test_models.py
tests/memory/test_store.py
tests/memory/test_context_ranker.py
tests/memory/test_context_manager.py
tests/evaluation/test_context_guardrails.py
```

## 必测场景

- rejected memory 不进入 ContextPack。
- stale memory 进入时产生 warning。
- domain prior 不能支撑 factual claim。
- hypothesis edge 不能作为 confirmed fact。
- duplicate evidence 被 hash dedupe。
- context score 排序稳定。
- token budget 超限会截断。
- contradiction evidence 可被保留。
- SQLite upsert 幂等。

## Workflow Tests

后续新增：

```text
tests/supply_chain/test_context_memory_integration.py
tests/workflows/test_finrisk_context_memory_integration.py
```

## Acceptance Commands

```bash
uv run pytest tests/memory tests/evaluation/test_context_guardrails.py -q
uv run ruff check src/memory tests/memory tests/evaluation/test_context_guardrails.py
```
