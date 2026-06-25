# 03 - V16 State、RiskScore 与 Structured Report 主路径

## 目标

将 V16 schema、RiskScoreV16、RiskReportV16 从“旁路字段”推进为主路径，同时保持旧 API 和前端兼容。

## 当前问题

`FinRiskWorkflowState` 中部分 V16 字段仍是：

```python
list
Any
```

主 workflow 仍以 V15 `RiskScore` / `RiskReport` 为主，V16 report 只是附加产物。

## 涉及文件

```text
src/schemas/finrisk.py
src/schemas/finrisk_v16.py
src/workflows/steps/risk_scorer.py
src/workflows/steps/report_generator.py
src/reports/models.py
src/reports/renderer.py
src/api/workflows.py
frontend/src/types.ts
frontend/src/components/RiskReport.tsx
frontend/src/components/RiskScoreBreakdown.tsx
tests/schemas/test_finrisk_v16_state.py
tests/workflows/test_risk_scoring.py
tests/reports/test_report_renderer.py
tests/api/test_workflow_api.py
```

## Schema 强类型化

在 `src/schemas/finrisk_v16.py` 统一 re-export：

- `Claim`
- `StepEvaluation`
- `WorkflowEvaluationV16`
- `FallbackEvent`
- `GraphQueryContext`
- `CandidateGraphPath`
- `GraphInsightV16`
- `EvidenceGraphPayload`
- `RiskScoreV16`
- `RiskReportV16`

`FinRiskWorkflowState` 应尽量使用强类型：

```python
claims: list[Claim]
graph_payload: EvidenceGraphPayload | None
graph_insights_v16: list[GraphInsightV16]
evaluations: list[StepEvaluation]
workflow_evaluation: WorkflowEvaluationV16 | None
guardrail_findings: list[GuardrailFinding]
fallback_events: list[FallbackEvent]
risk_scores_v16: list[RiskScoreV16]
report_v16: RiskReportV16 | None
```

如确有循环引用，用 `TYPE_CHECKING`、延迟 import 或 re-export 拆解，不继续扩大 `Any`。

## RiskScoreV16 主路径

`RiskScorerStep` 必须生成：

```python
state.risk_scores_v16
```

要求：

- 分数范围 0-100。
- 包含 score breakdown。
- breakdown 字段和 V16 spec 一致。
- V15 `state.risk_scores` 可由 V16 adapter 降级生成，或继续并行保留。

推荐字段：

```text
base_severity
recent_signal_strength
evidence_quality
source_diversity
novelty_score
graph_centrality
final_score
confidence
reasoning
```

## RiskReportV16 主路径

`ReportGeneratorStep` 改为：

```text
RiskReportV16 model
→ ReportStructureValidator
→ render_risk_report_markdown()
→ legacy RiskReport adapter
```

报告必须包含：

- title
- executive_summary
- top_risks
- risk_scores
- evidence_references
- recent_changes
- graph_insights
- evidence_vs_inference
- limitations
- disclaimer
- recommended_next_questions

要求：

- 所有 claim 有 evidence ids。
- disclaimer 必须存在。
- 不输出直接 buy/sell/guaranteed return。
- markdown 只能由 renderer 生成，不在 step 中手拼大段报告。

## API 与前端

`GET /workflows/{run_id}/report` 返回：

```json
{
  "report": "legacy",
  "report_v16": "structured",
  "markdown": "rendered markdown"
}
```

前端优先消费：

```text
report_v16
```

如果为空，再 fallback 到 legacy report。

## 测试要求

新增或增强：

```text
tests/schemas/test_finrisk_v16_state.py
tests/workflows/test_risk_scoring.py
tests/reports/test_report_renderer.py
tests/api/test_workflow_api.py
frontend/src/components/RiskReport.test.tsx
frontend/src/components/RiskScoreBreakdown.test.tsx
```

测试用例：

- state 可 JSON round-trip。
- invalid graph path schema 被 Pydantic 拦截。
- invalid StepEvaluation schema 被 Pydantic 拦截。
- `RiskScoreV16.final_score` 在 0-100。
- score breakdown 字段完整。
- report_v16 有 disclaimer。
- report_v16 claims 都有 evidence ids。
- markdown 由 renderer 输出。
- frontend 优先渲染 report_v16。

验收命令：

```bash
uv run pytest tests/schemas/test_finrisk_v16_state.py -q
uv run pytest tests/workflows/test_risk_scoring.py tests/reports/test_report_renderer.py tests/api/test_workflow_api.py -q
cd frontend && npm test -- --run RiskReport RiskScoreBreakdown
```

