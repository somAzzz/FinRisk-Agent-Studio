# 07 - API, UI Trace, and Human Review

## 目标

把 V21 agent run 暴露给本地/API/UI，使用户能看到 agent 为什么这样做、用了哪些工具、哪些证据被接受或拒绝，以及哪些结论需要 human review。

用户不计划公网部署 API，但本地或内网 API/UI 仍需要完整可观测性。

## API Contracts

新增或扩展 API：

- `POST /agent-runs`
  - 输入：goal、workflow_kind、provider、tool_loop_mode、tool_scope、demo/cached flags。
  - 输出：run_id、status。
- `GET /agent-runs/{run_id}`
  - 输出：`AgentRunState` summary。
- `GET /agent-runs/{run_id}/timeline`
  - 输出：decisions、subgoals、tool calls、candidate evidence。
- `GET /agent-runs/{run_id}/trace.json`
  - 输出：完整可下载 trace。
- `POST /agent-runs/{run_id}/review-items/{item_id}`
  - 输入：approve / reject / comment。

## UI Views

新增或扩展 UI tabs：

- Agent Timeline
- Planner Decisions
- Tool Calls
- Evidence Candidates
- Accepted Evidence
- Uncertainty / Review Queue
- Final Report / Sankey / Graph

UI 必须区分：

- evidence
- inference
- uncertainty
- rejected candidate
- human-approved item

## Human Review Model

新增 `HumanReviewItem`：

- `item_id`
- `run_id`
- `subgoal_id`
- `object_type`: evidence_candidate / supplier_candidate / graph_path / report_claim
- `object_id`
- `reason`
- `suggested_action`
- `status`: pending / approved / rejected
- `reviewer_comment`
- `created_at`
- `reviewed_at`

Review action 可触发：

- candidate accepted。
- candidate rejected。
- edge write approved。
- report claim approved。
- run marked needs_review / completed。

## Storage

Agent run state 可先复用现有 run store 模式：

- in-memory store for tests / demo。
- SQLite store for local persistence。

Trace JSON 必须可序列化，不包含 secrets。

## Redaction

API/UI 输出必须 redacts：

- API keys。
- auth headers。
- raw provider client config。
- `.env` values。

工具 arguments 和 result summary 也必须通过现有 redaction helper。

## 测试

新增：

```text
tests/api/test_agent_runs_api.py
tests/api/test_agent_trace_redaction.py
```

如前端存在对应 app，新增：

```text
frontend tests for Agent Timeline / Review Queue
```

覆盖：

- start agent run。
- get run timeline。
- download trace JSON。
- review approve/reject。
- trace 不泄露 secret。
- failed run 仍可读取 trace。

## 验收

```bash
uv run pytest tests/api/test_agent_runs_api.py tests/api/test_agent_trace_redaction.py -q
```
