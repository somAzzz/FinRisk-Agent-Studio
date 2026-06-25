# 03 - Evidence Memory Store

## 目标

用 SQLite 实现 MVP memory store，后续可迁移到 SQLite + vector index / Postgres / Neo4j hybrid。

## 文件

```text
src/memory/store.py
```

默认数据库：

```text
.cache/fintext_llm/memory.sqlite
```

## API

必须支持：

- `upsert(item)`
- `get(memory_id)`
- `search_candidates(subject, intent, limit)`
- `mark_used(memory_id)`
- `mark_rejected(memory_id, reason)`
- `mark_stale(memory_id, reason)`
- `list_by_entity(entity)`
- `list_by_run(run_id)`

## 写入来源

MVP 支持：

- `Evidence`
- `NormalizedSupplyChainEvidence`
- manual `MemoryItem`

后续支持：

- SearchRouter response。
- graph edge。
- report claim。
- user feedback。

## Dedupe

使用 text + source_url + source_type 生成 hash。

同 hash 写入时更新：

- `last_seen_at`
- `provenance`
- `confidence`

## 验收

- SQLite schema 自动创建。
- upsert 幂等。
- status 更新可持久化。
- search 不返回 rejected。
