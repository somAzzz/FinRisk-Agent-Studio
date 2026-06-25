# 02 - V16 Graph Payload Contract

## 目标

修复 Graph API 返回 V15/V16 insight 类型错位的问题，使 `/workflows/{run_id}/graph` 返回完整 V16 `EvidenceGraphPayload`。

当前问题：

```text
GraphReasonerStep 运行 V16 subsystem
→ state.graph_paths 保存了 paths
→ API insights 仍返回 V15 state.graph_insights
```

目标：

```text
state.graph_payload = EvidenceGraphPayload
state.graph_insights_v16 = list[GraphInsightV16]
GET /graph returns graph_payload
```

## 涉及文件

```text
src/workflows/state.py
src/schemas/finrisk.py
src/schemas/finrisk_v16.py
src/workflows/steps/graph_reasoner.py
src/api/workflows.py
src/graph_reasoning/models.py
tests/api/test_quality_graph_api.py
tests/graph_reasoning/test_graph_reasoner_step.py
tests/api/test_v16_payload_contract.py
```

## State 字段

新增或确认：

```python
graph_payload: EvidenceGraphPayload | None = None
graph_insights_v16: list[GraphInsightV16] = Field(default_factory=list)
```

如果存在 import cycle，使用：

```text
src/schemas/finrisk_v16.py
```

做 re-export，避免 workflow state 直接知道子模块细节。

## GraphReasonerStep 行为

运行：

```python
payload = self._v16.run(state)
```

必须保存：

```python
state.graph_payload = payload
state.graph_paths = [p.model_dump() for p in payload.paths]
state.graph_insights_v16 = list(payload.insights)
state.graph_context = payload.paths[0].model_dump() if payload.paths else None
```

保留：

```python
state.graph_insights
```

用于 V15 legacy report compatibility。

## API 行为

`GET /workflows/{run_id}/graph` 优先返回：

```python
state.graph_payload.model_dump(mode="json")
```

fallback：

```text
如果 graph_payload 为空，用 graph_paths / graph_insights 构造 backward-compatible payload。
```

返回字段：

```json
{
  "nodes": [],
  "edges": [],
  "paths": [],
  "insights": [],
  "guardrail_findings": []
}
```

V16 insight 必须包含：

- `insight_id`
- `source_company`
- `insight_type`
- `risk_path_ids`
- `affected_entities`
- `explanation`
- `evidence_ids`
- `confidence`
- `uncertainty`
- `recommended_next_questions`
- `research_theme`

## Contract 校验

新增测试应该验证：

- 每个 `insight.risk_path_ids` 都存在于 `paths.path_id`。
- 每个 `insight.evidence_ids` 都存在于 `state.normalized_evidence`。
- `guardrail_findings` 可序列化。
- `/graph` payload 可 JSON round-trip。
- 前端需要的字段不缺失。

## 测试要求

新增或增强：

```text
tests/api/test_quality_graph_api.py
tests/graph_reasoning/test_graph_reasoner_step.py
tests/api/test_v16_payload_contract.py
```

测试用例：

- `/graph.insights[0]` 包含 `risk_path_ids`。
- `/graph.insights[0]` 包含 `affected_entities`。
- insight 引用 path id 存在。
- insight 引用 evidence id 存在。
- `state.graph_payload` 不为空。
- `state.graph_insights_v16` 不为空。
- legacy `state.graph_insights` 仍可用于 report。

验收命令：

```bash
uv run pytest tests/api/test_quality_graph_api.py tests/api/test_v16_payload_contract.py -q
uv run pytest tests/graph_reasoning/test_graph_reasoner_step.py -q
```

