# 03 - Global Agent Runtime and Subgoal Loop

## 目标

在 V20 `LLMToolAgentRuntime` 上方增加全局 agent runtime。V20 runtime 负责“一个 goal 里调工具”；V21 runtime 负责“一个用户任务里规划 subgoals、循环执行、吸收 evidence、决定停止”。

## 当前基线

已有：

- `LLMToolAgentRuntime.run(goal) -> LLMToolRunResult`
- `ToolCatalog` scopes
- `ToolLoopTrace`
- local `json_fallback` / `auto`

缺口：

- 没有 subgoal queue。
- 没有跨 subgoal budget。
- 没有统一 stop/review/fallback。
- 没有把 evidence normalizer 接进 runtime。

## 新增 Runtime

建议新增：

```text
src/agents/global_runtime.py
```

核心类：

- `GlobalAgentRuntime`
- `AgentPlanner`
- `AgentBudgetManager`
- `AgentRunRecorder`

主入口：

```python
GlobalAgentRuntime.run(
    user_goal: str,
    workflow_kind: str,
    *,
    provider: str,
    tool_scope: str,
    mode: Literal["shadow", "primary", "review_first"],
) -> AgentRunState
```

## Loop 流程

```text
initialize AgentRunState
planner creates initial subgoals
while budget remains:
  choose next pending subgoal
  planner decides tool scope / success criteria
  LLMToolAgentRuntime runs subgoal
  append ToolLoopTrace
  normalize ToolExecutionEvents -> EvidenceCandidates
  validators accept/reject/review candidates
  planner decides continue / add subgoals / fallback / review / stop
finalize AgentRunState
```

## Budget

新增 `AgentBudget`：

- `max_subgoals`
- `max_tool_rounds_per_subgoal`
- `max_total_tool_calls`
- `max_total_fetch_pages`
- `max_total_runtime_seconds`
- `max_total_tool_result_chars`

默认：

- FinRisk primary：最多 8 个 subgoals。
- Supply Chain primary：每个 requirement 最多 2 个 supplier subgoals。
- Generic research：最多 5 个 subgoals。

## Stop Conditions

必须支持：

- enough evidence。
- budget exhausted。
- repeated tool failures。
- low confidence / no accepted evidence。
- human review required。
- deterministic fallback completed。

每次 stop 必须写入 `AgentDecision(stop_reason=...)`。

## Error Handling

- Tool exception：记录 failed `ToolExecutionEvent`，planner 可重试或 fallback。
- Planner parse failure：deterministic planner fallback。
- Evidence normalizer failure：该 candidate rejected，不中断 run。
- LLM unavailable：workflow fallback 或 `needs_review`。

## Integration Points

第一版 runtime 不替换所有 workflow。接入顺序：

1. FinRisk agent primary wrapper。
2. Supply Chain supplier discovery primary wrapper。
3. API runner。
4. UI trace。

## 测试

新增：

```text
tests/agents/test_global_agent_runtime.py
tests/agents/test_agent_budget.py
```

覆盖：

- runtime 初始化 `AgentRunState`。
- planner subgoals 被执行。
- tool events 进入 candidates。
- budget exhausted 产生 stop decision。
- failed tool call 不崩溃。
- bad planner JSON 触发 deterministic fallback。
- local LLM `auto` mode trace 记录实际 fallback mode。

## 验收

```bash
uv run pytest tests/agents/test_global_agent_runtime.py tests/agents/test_agent_budget.py -q
```
