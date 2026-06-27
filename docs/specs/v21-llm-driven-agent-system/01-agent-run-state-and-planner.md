# 01 - Agent Run State and Planner

## 目标

新增全局 agent 状态模型，让用户目标先进入可审计的 `AgentRunState`，再由 planner 拆成 subgoals。V21 不能再只依赖固定 workflow step 顺序；workflow 仍存在，但 agent 需要决定先查什么、何时补证据、何时停止或进入 human review。

## 当前基线

V20 已有：

- `LLMToolAgentRuntime`：单个 goal 的 tool loop。
- `LLMToolRunResult`：final answer、tool calls、tool events、LLM audit log。
- `ToolLoopTrace`：工具执行 trace。

缺口：

- 没有跨 subgoal 的 run state。
- 没有 planner decision schema。
- 没有 stop / fallback / review 的结构化原因。
- 没有 subgoal queue 和 progress 状态。

## 新增模型

建议新增 `src/agents/state.py` 或同等模块，定义：

```python
AgentRunStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "needs_review",
]

AgentSubgoalStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "skipped",
    "needs_review",
]

AgentStopReason = Literal[
    "enough_evidence",
    "budget_exhausted",
    "tool_failures",
    "low_confidence",
    "human_review_required",
    "user_cancelled",
]
```

核心 Pydantic models：

- `AgentRunState`
  - `run_id`
  - `user_goal`
  - `workflow_kind`: `finrisk | supply_chain | company_research | generic_research`
  - `status`
  - `subgoals`
  - `decisions`
  - `tool_traces`
  - `evidence_candidates`
  - `accepted_evidence_ids`
  - `fallback_events`
  - `human_review_items`
  - `budget`
  - `created_at` / `updated_at`
- `AgentSubgoal`
  - `subgoal_id`
  - `parent_subgoal_id`
  - `objective`
  - `status`
  - `tool_scope`
  - `required_evidence_types`
  - `success_criteria`
  - `attempt_count`
  - `depends_on`
- `AgentDecision`
  - `decision_id`
  - `subgoal_id`
  - `decision_type`: `plan | call_tools | accept_evidence | ask_review | fallback | stop`
  - `rationale`
  - `selected_tools`
  - `next_subgoals`
  - `stop_reason`
  - `confidence`
  - `created_at`

## Planner Contract

Planner 输入：

- user goal
- workflow kind
- current `AgentRunState`
- available tool scopes
- evidence already accepted
- open uncertainty / review items
- remaining budget

Planner 输出必须是结构化 `AgentDecision`，不能只返回自然语言。

最低支持 decision types：

1. `plan`: 初始化或补充 subgoals。
2. `call_tools`: 对当前 subgoal 运行 `LLMToolAgentRuntime`。
3. `accept_evidence`: 请求 normalizer / validator 接受候选证据。
4. `fallback`: 切回 deterministic path。
5. `ask_review`: 标记 human review。
6. `stop`: 带 `AgentStopReason` 完成。

## 默认 Planner 策略

第一版使用 LLM structured output planner + deterministic fallback：

- LLM 可生成 subgoals 和 decision rationale。
- 如果 planner 输出不可解析，使用 deterministic planner：
  - FinRisk：filing -> market -> transcript/financial -> graph -> report。
  - Supply Chain：product -> requirements -> supplier discovery -> graph -> sankey。
- 每次 planner 决策都进入 `AgentRunState.decisions`。

## Guardrails

- Planner 只能选择 catalog 中存在的 tool scope。
- Planner 不能请求 write tool。
- Planner 不能直接写 workflow state。
- Planner 对 high-impact conclusion 必须设置 success criteria 和 evidence requirement。
- Planner 对证据不足的 subgoal 必须选择 `fallback`、`ask_review` 或继续查证，不能直接 `stop`。

## 测试

新增：

```text
tests/agents/test_agent_state.py
tests/agents/test_agent_planner.py
```

覆盖：

- `AgentRunState` JSON round-trip。
- planner 输出 subgoals。
- bad planner JSON 触发 deterministic fallback。
- planner 不能选择不存在的 tool scope。
- stop decision 必须带 `AgentStopReason`。
- human review decision 保留 uncertainty。

## 验收

```bash
uv run pytest tests/agents/test_agent_state.py tests/agents/test_agent_planner.py -q
```
