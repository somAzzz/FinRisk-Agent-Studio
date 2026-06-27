# 02 - Unified Evidence Candidate Normalizer

## 目标

建立统一证据候选层，把所有 LLM 工具结果从 `ToolExecutionEvent` 规范化为 `EvidenceCandidate`，再由 workflow-specific validators 转成正式证据。

V21 的关键原则：

```text
LLM final answer is not evidence.
Tool output may become candidate evidence.
Only validated candidate evidence enters workflow state.
```

## 当前基线

V20 已有：

- `ToolExecutionEvent`
- `ToolLoopTrace`
- `MarketExplorerStep` 内部从 tool event 临时转换 `MarketEvidence`。
- Supply Chain supplier discovery shadow 从 tool event 临时抽 `SupplierCandidate`。

缺口：

- FinRisk / Supply Chain 各自解析工具输出，逻辑会漂移。
- 没有统一 source quality / grounding / entity binding。
- 没有统一候选证据生命周期。

## 新增模型

建议新增 `src/evidence/candidates.py`：

```python
EvidenceCandidateStatus = Literal[
    "candidate",
    "accepted",
    "rejected",
    "needs_review",
]

EvidenceCandidateKind = Literal[
    "web",
    "filing",
    "transcript",
    "financial_metric",
    "graph_path",
    "browser",
]
```

`EvidenceCandidate` 字段：

- `candidate_id`
- `source_tool`
- `source_event_id`
- `kind`
- `source_url`
- `source_title`
- `quote`
- `summary`
- `entities`
- `related_subgoal_id`
- `related_risk_ids`
- `related_node_ids`
- `confidence`
- `source_quality_score`
- `grounding_score`
- `status`
- `rejection_reason`
- `created_at`
- `metadata`

## Normalizer Pipeline

新增 `EvidenceCandidateNormalizer`：

```text
ToolExecutionEvent
  -> parse tool envelope
  -> extract candidate rows
  -> classify source kind
  -> attach source metadata
  -> compute source quality
  -> compute lexical grounding against subgoal / claim
  -> bind entities
  -> dedupe
  -> emit EvidenceCandidate
```

工具映射：

- `web_search`: 每个 search result snippet 生成 web candidate。
- `web_fetch`: page content 生成 web/browser candidate。
- `search_and_fetch`: search results + fetched pages 合并去重。
- `sec_fetch_filing`: filing section 生成 filing candidate。
- `transcript_lookup`: transcript turns 生成 transcript candidate。
- `financial_metrics_lookup`: metrics rows 生成 financial_metric candidate。
- `xbrl_fact_lookup`: facts rows 生成 financial_metric candidate。
- `graph_query` / `graph_path_search`: candidate path 生成 graph_path candidate。
- `browser_explore`: findings 生成 browser candidate。

## Acceptance Rules

默认接受条件：

- `source_url` 为 http(s)，或来源是 SEC filing / XBRL internal source。
- `quote` 或 `summary` 非空。
- `source_quality_score >= 0.5`。
- `grounding_score >= 0.25`，否则 `needs_review`。
- duplicate candidates 合并 source metadata。

默认拒绝条件：

- tool event status failed。
- unknown tool。
- empty quote/summary。
- private / invalid URL。
- LLM-only statement without source event。

## Workflow Adapters

新增 adapter：

- `FinRiskEvidenceAdapter`
  - `EvidenceCandidate -> MarketEvidence`
  - `EvidenceCandidate -> NormalizedEvidence`
- `SupplyChainEvidenceAdapter`
  - `EvidenceCandidate -> NormalizedSupplyChainEvidence`
  - candidate evidence ids 可绑定到 `SupplierCandidate`
- `GraphEvidenceAdapter`
  - `EvidenceCandidate -> graph path support metadata`

Adapters 不做 tool parsing，只消费 normalized candidates。

## Guardrails

- final report 只能引用 accepted evidence。
- confirmed supplier edge 必须引用 accepted evidence。
- graph insight 必须引用 accepted graph_path 或 source evidence。
- low-quality candidates 保留在 trace，但不进入正式 report/table。

## 测试

新增：

```text
tests/evidence/test_evidence_candidate_normalizer.py
tests/evidence/test_workflow_evidence_adapters.py
```

覆盖：

- web search event -> web candidates。
- web fetch event -> content candidate。
- transcript event -> transcript candidate。
- graph path event -> graph_path candidate。
- failed tool event 被拒绝。
- duplicate URLs 合并。
- LLM final answer 不会生成 evidence。
- adapters 只接受 accepted candidates。

## 验收

```bash
uv run pytest tests/evidence -q
```
