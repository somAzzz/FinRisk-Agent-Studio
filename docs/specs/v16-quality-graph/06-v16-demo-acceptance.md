# V16 Spec 06 - Demo 验收标准

## 目标

定义第 16 版 FinRisk Agent Studio 的最终验收标准。

## 必须支持的 demo 命令

```bash
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify macro, policy and supply-chain risks that changed recently." \
  --demo-mode
```

## CLI 输出必须包含

- run_id。
- final status。
- completed steps。
- fallback events。
- guardrail summary。
- top risks。
- graph path summary。
- report path 或 markdown。

## Workflow state 必须包含

- `trace`
- `evaluations`
- `guardrail_findings`
- `fallback_events`
- `claims`
- `normalized_evidence`
- `risk_scores`
- `graph_context`
- `graph_paths`
- `graph_insights`
- `report`
- `workflow_evaluation`
- `artifacts`

## Demo fixture 要求

至少包含：

- 3 条 filing risks。
- 5 条 normalized evidence。
- 5 条 claims。
- 3 条 candidate graph paths。
- 2 条 ranked graph paths。
- 1 条 graph insight。
- 1 条 source quality warning 或 fallback event。
- 1 条 needs_review guardrail finding，用于展示 Evaluation tab。

## Guardrail 验收

必须验证：

- 每个 top risk 有 evidence。
- 每个 claim 有 supporting evidence ids。
- unsupported claim 会进入 guardrail findings。
- financial advice phrase 会触发 warning/needs_review。
- missing graph path 会触发 blocker。
- no primary source 会触发 needs_review。
- fallback events 会记录。

## Graph 验收

必须验证：

- graph path 不由 LLM 编造。
- insight 引用的 path_id 存在。
- insight evidence_ids 存在。
- confidence 不超过 path_score 过多。
- 无 evidence edge 被标记为 hypothesis 或 warning。
- graph payload 可被前端渲染。

## Report 验收

必须验证：

- report 是结构化 model。
- markdown 是 renderer 输出。
- report 包含 disclaimer。
- report 包含 limitations。
- report 包含 evidence_vs_inference。
- report 无直接 buy/sell advice。
- report claim 可以跳转 graph。

## API 验收

必须支持：

```text
POST /workflows/finrisk/run
GET  /workflows/{run_id}
GET  /workflows/{run_id}/trace
GET  /workflows/{run_id}/report
GET  /workflows/{run_id}/graph
GET  /workflows/{run_id}/evaluation
```

## 前端验收

必须展示：

- Launcher。
- Timeline。
- Risk Report。
- Evidence Graph。
- Evaluation tab。
- Claim-Evidence Matrix。
- Risk Score Breakdown。
- Guardrail Findings Drawer。

## 测试命令

```bash
uv run pytest -q
uv run pytest tests/evaluation -q
uv run pytest tests/graph_reasoning -q
uv run pytest tests/workflows -q
uv run python -m src.workflows.finrisk_workflow --ticker AAPL --demo-mode
```

如果前端已实现：

```bash
cd frontend
npm run build
```

## 非目标

第 16 版不要求：

- 真实 Neo4j 必须可用。
- 真实 browser 必须可用。
- 真实 LLM judge 必须可用。
- 真实 SEC 网络请求必须可用。
- 完整交易或投资建议。

## 完成定义

第 16 版完成时，demo 应该能清楚展示：

```text
这是一个有质量层的 agent workflow，
每个 step 都被验证，
每个 claim 都能追溯 evidence，
每条 graph insight 都来自真实路径，
每个风险分数都能解释，
每个 warning 都能被 human review。
```

