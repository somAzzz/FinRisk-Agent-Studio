# 10 - Phase 2 Evidence / Graph Memory Progress

## 本轮目标

将 v19 从 MVP ContextPack 层推进到 Phase 2 的最小工程切片：

- 现有 evidence schema 可以进入 MemoryStore。
- v18 supply-chain evidence 可以进入 MemoryStore。
- v18 supply-chain edge 可以进入 graph-edge memory。
- 写入前执行 Memory Write Guardrails。
- hypothesis / untrusted web / LLM extracted memory 不直接进入 active memory。

## 新增模块

```text
src/memory/adapters.py
src/memory/ingestion.py
src/evaluation/memory_guardrails.py
```

## 行为

### Evidence adapters

支持：

- `Evidence -> MemoryItem`
- `NormalizedSupplyChainEvidence -> MemoryItem`
- `SupplyChainEdge -> graph_edge MemoryItem`

source type 映射：

```text
sec_filing / sec_xbrl / edgar_corpus -> filing
browser -> web
manual -> manual
fixture -> fixture
```

### MemoryWriteGuardrails

规则：

- `hypothesis + active` 降级为 `candidate`。
- `web/news + active` 降级为 `candidate`。
- `provenance.extracted_by == llm + active` 降级为 `candidate`。
- `domain_prior + claim_type=evidence` 阻断。

### GraphMemoryGuardrails

规则：

- confirmed edge 必须有 evidence。
- hypothesized edge 写为 candidate。
- confirmed edge 写为 active。

## 后续

下一阶段可以把这些 adapter 接入：

- `SupplierDiscoveryStep`
- `EvidenceNormalizerStep`
- `GraphBuilderStep`
- FinRisk `EvidenceNormalizerStep`
