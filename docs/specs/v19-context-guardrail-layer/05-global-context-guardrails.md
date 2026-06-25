# 05 - Global Context Guardrails

## 目标

把 Guardrails 从最终报告检查扩展到 context read / write / pack / claim / graph 全流程。

## ContextPack Guardrails

必须检查：

- `context_budget_valid`
- `evidence_minimum_met`
- `source_diversity_valid`
- `freshness_valid`
- `primary_source_required`
- `no_rejected_memory`
- `hypothesis_labeled`
- `contradiction_included`
- `negative_memory_included`
- `context_manifest_complete`

## Memory Write Guardrails

必须检查：

- schema valid。
- source present。
- quote/text not empty。
- hash dedupe。
- temporal metadata valid。
- credibility score assigned。
- claim type valid。
- LLM extracted item cannot become active directly。

## Claim Grounding Guardrails

必须检查：

- claim has memory binding。
- evidence still active。
- claim not based on stale-only evidence。
- domain prior cannot support factual claim。
- claim checked against counterevidence。
- claim traceable to ContextPack。

## Memory Poisoning Guardrails

必须检查：

- duplicate content cluster。
- low credibility cluster。
- source spam。
- untrusted web memory quarantine。
- human rejected override。

## 验收

- rejected memory 进入 ContextPack 时 fail。
- stale-only factual claim needs review。
- domain prior factual claim fail。
- missing manifest fail。
