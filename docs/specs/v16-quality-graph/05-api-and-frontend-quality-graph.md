# V16 Spec 05 - API 与前端的 Quality / Graph 展示

## 目标

升级 API 和前端，让 Evaluation 与 Graph Reasoning 成为 demo 可见亮点。

## API 升级

保留：

```text
POST /workflows/finrisk/run
GET  /workflows/{run_id}
GET  /workflows/{run_id}/report
```

新增或预留：

```text
GET /workflows/{run_id}/trace
GET /workflows/{run_id}/graph
GET /workflows/{run_id}/evaluation
GET /workflows/{run_id}/artifacts
```

## Endpoint 规格

### `GET /workflows/{run_id}/evaluation`

返回：

```json
{
  "run_id": "...",
  "final_status": "needs_review",
  "overall_metrics": {},
  "blocker_count": 0,
  "warning_count": 3,
  "unsupported_claims": [],
  "human_review_required": true,
  "step_evaluations": []
}
```

### `GET /workflows/{run_id}/graph`

返回：

```json
{
  "nodes": [],
  "edges": [],
  "paths": [],
  "insights": [],
  "guardrail_findings": []
}
```

### `GET /workflows/{run_id}/trace`

返回：

```json
{
  "run_id": "...",
  "trace": [],
  "fallback_events": []
}
```

## Frontend tabs

第 16 版前端为 5 个 tab：

```text
1. Launcher
2. Timeline
3. Risk Report
4. Evidence Graph
5. Evaluation
```

## Evaluation tab

必须包含 5 个组件。

### Evaluation Overview

展示：

- Final Status
- Schema Validity
- Evidence Coverage
- Unsupported Claims
- Financial Advice Risk
- Graph Path Validity
- Source Diversity
- Human Review Required

### Step Quality Timeline

展示每个 step：

- step name
- status
- warning count
- blocker count
- latency
- fallback used

### Claim-Evidence Matrix

表格列：

```text
Claim
Type
Evidence
Grounding
Status
Recommendation
```

### Risk Score Breakdown

对每个 top risk 展示：

- base severity
- recent signal strength
- evidence quality
- source diversity
- novelty
- graph centrality
- final score

### Guardrail Findings Drawer

点击 finding 展示：

- finding id
- step
- check
- affected object
- severity
- message
- recommendation

## Evidence Graph tab

节点类型：

- Company
- Risk
- Evidence
- Supplier
- Region
- Policy
- Insight

边样式：

```text
solid edge      evidence-backed
dashed edge     hypothesis
red border      needs review
thick edge      high confidence
thin edge       low confidence
```

点击节点侧边栏：

- Risk: severity, score, evidence coverage, guardrail findings。
- Path: path score, evidence, insight, guardrail status。
- Evidence: source quality, quote, URL。

Report 联动：

- report claim 点击 `View evidence graph`。
- 图中高亮 claim → evidence → path → insight。

## UX 验收

- Evaluation 不隐藏在 timeline 中。
- needs_review 状态不能只显示一个黄色标签，必须显示原因。
- graph insight 必须能追溯到 path 和 evidence。
- fallback events 必须可见。

## Tests

后端：

```text
tests/api/test_quality_graph_api.py
```

前端：

- evaluation tab fixture render。
- graph fixture render。
- claim-evidence matrix render。
- risk score breakdown render。

## 验收命令

```bash
uv run pytest tests/api/test_quality_graph_api.py -q
```

前端按项目 package script：

```bash
cd frontend
npm run build
```

