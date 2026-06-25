# 01 - Memory Models 与 Lifecycle

## 核心模型

新增 `src/memory/models.py`。

必须包含：

- `MemoryItem`
- `ContextCandidate`
- `ContextPack`
- `ContextPackEvaluation`
- `WorkflowEpisode`
- `MemoryWriteDecision`
- `MemoryReadDecision`

## MemoryItem

字段要求：

- `memory_id`
- `memory_type`: `evidence`, `graph_edge`, `claim`, `episode`, `domain_prior`, `policy`
- `text`
- `summary`
- `source_type`: `filing`, `company`, `regulatory`, `news`, `transcript`, `web`, `graph`, `domain_prior`, `human_feedback`, `fixture`
- `source_url`
- `source_title`
- `entities`
- `tickers`
- `products`
- `risks`
- `published_at`
- `retrieved_at`
- `first_seen_at`
- `last_used_at`
- `credibility_score`
- `freshness_score`
- `confidence`
- `claim_type`: `evidence`, `inference`, `hypothesis`, `policy`
- `status`: `candidate`, `validated`, `active`, `used`, `stale`, `superseded`, `rejected`, `deprecated`
- `hash`
- `embedding_id`
- `provenance`

## Lifecycle

```text
candidate
→ validated
→ active
→ used
→ stale / superseded / rejected / deprecated
```

规则：

- LLM 输出不能直接写入 `active`。
- untrusted web evidence 默认进入 `candidate`。
- filing / company / regulatory source 可以更快晋升到 `validated`。
- `rejected` 不允许进入 ContextPack。
- `stale` 可以进入 ContextPack，但必须生成 warning。
- `domain_prior` 只能用于 decomposition / query expansion。
- `hypothesis` 不能作为 final factual claim。

## 验收

- Pydantic extra forbid。
- score 字段范围为 0 到 1。
- 空 text 不允许。
- `memory_id` 稳定可序列化。
