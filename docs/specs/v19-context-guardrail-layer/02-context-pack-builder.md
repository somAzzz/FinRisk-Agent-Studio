# 02 - ContextPack Builder

## 目标

`ContextManager` 在每个 workflow step 执行前构造 `ContextPack`，替代“把完整 state 给 LLM”。

## 入口

```python
context_pack = context_manager.build(
    run_id=...,
    step_name=...,
    task=...,
    subject=...,
    intent=...,
    token_budget=...,
)
```

## 输出

`ContextPack` 必须包含：

- `context_pack_id`
- `run_id`
- `step_name`
- `task`
- `objective`
- `constraints`
- `selected_memory_ids`
- `rejected_memory_ids`
- `selected_evidence`
- `selected_graph_paths`
- `prior_findings`
- `negative_memory`
- `exclusions`
- `token_budget`
- `estimated_tokens`
- `freshness_window_days`
- `selection_policy_version`
- `warnings`

## Ranking Policy

MVP 使用 deterministic scoring：

```text
context_score =
  0.25 semantic_relevance
+ 0.20 source_credibility
+ 0.15 freshness
+ 0.15 graph_proximity
+ 0.10 evidence_diversity
+ 0.10 prior_success_score
+ 0.10 primary_source_bonus
+ 0.10 contradiction_bonus
- 0.20 staleness_penalty
- 0.20 duplicate_penalty
- 0.50 rejected_memory_penalty
```

MVP 中：

- `semantic_relevance` = subject / task keyword overlap。
- `source_credibility` = stored credibility score。
- `freshness` = stored freshness score。
- `graph_proximity` = 由 provenance 或 entity overlap 推断。
- `primary_source_bonus` = filing / company / regulatory source。

## Compression

MVP 不做 LLM summarization，只做字符级裁剪：

- evidence quote 最大 600 chars。
- summary 最大 300 chars。
- selected items 不超过 token budget。

## 验收

- rejected memory 永不 selected。
- stale memory selected 时必须 warning。
- selected / rejected manifest 完整。
- 超预算时按 score 截断。
