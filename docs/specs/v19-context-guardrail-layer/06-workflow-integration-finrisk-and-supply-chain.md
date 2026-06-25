# 06 - Workflow Integration

## 优先级

先接入 v18 Supply Chain，再接入 FinRisk。

## Supply Chain 接入点

```text
Product Resolver
→ ContextPack build
Requirement Decomposer
→ ContextPack build
Supplier Discovery
→ Memory write validation
Evidence Normalizer
→ Evidence Memory write
Graph Builder
→ Graph Memory write validation
Sankey Builder
→ Context / Graph Guardrails
```

Trace 需要记录：

- `context_pack_id`
- `selected_memory_count`
- `rejected_memory_count`
- `stale_memory_count`
- `memory_write_count`
- `memory_read_count`
- `guardrail_findings`

## FinRisk 接入点

```text
Company Resolver
→ no memory required
Filing Risk Extractor
→ write filing evidence memory
Market Explorer
→ build context from prior evidence and counterevidence
Evidence Normalizer
→ memory write validation
Risk Scorer
→ read evidence context
Graph Reasoner
→ graph memory context
Report Generator
→ claim-memory grounding
```

## 验收

- v18 demo workflow 不因 memory unavailable 失败。
- memory unavailable 时 fallback to no-memory context。
- trace 记录 fallback。
- cached mode 不依赖外部 API。
