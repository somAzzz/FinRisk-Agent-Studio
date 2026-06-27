# V21 LLM-driven Agent System Specs - Index

## 目标

V21 承接 V20 的 tool loop，把 FinText-LLM 从“局部步骤可由 LLM 调工具”升级为“全局目标由 LLM planner 驱动，后端受控执行，workflow 负责验证和写入”的 agent system。

核心变化：

```text
V20: LLM chooses tools inside selected steps.
V21: LLM plans subgoals, chooses tools, consumes evidence candidates, and decides stop/review/fallback.
```

V21 仍保持 evidence-first 和 write-gated 原则：

- read tools 可由 LLM 选择。
- write tools 不直接暴露给 LLM。
- 所有工具结果先进入 `EvidenceCandidate`。
- 报告、图写入、memory 写入由 deterministic workflow 和 guardrails 控制。

## 与现有版本关系

- V15：提供 FinRisk Agent Studio workflow 和 UI 基线。
- V16：提供 quality layer、claim grounding、graph reasoning。
- V17：修复审计问题，强化 fallback 和 CI gate。
- V18：提供 Product Supply Chain Explorer。
- V19：提供 evidence-first context / memory guardrail layer。
- V20：提供 provider-neutral tool loop、ToolCatalog、trace、local fallback。
- V21：补齐全局 planner、AgentRunState、evidence candidate normalizer、primary agent workflows、API/UI trace 和 agent evaluation。

## 文件导航

```text
01-agent-run-state-and-planner.md
02-unified-evidence-candidate-normalizer.md
03-global-agent-runtime-and-subgoal-loop.md
04-finrisk-primary-agent-workflow.md
05-supply-chain-primary-agent-workflow.md
06-graph-browser-and-memory-closed-loop.md
07-api-ui-trace-and-human-review.md
08-evaluation-golden-cases-and-acceptance.md
```

## 执行原则

1. 不重写 V20：复用 `LLMToolAgentRuntime`、`ToolCatalog`、`ToolExecutionEvent`。
2. 不重写 workflow：在 FinRisk / Supply Chain 外层增加 agent orchestration。
3. 先 schema，再 runtime，再 workflow migration。
4. 工具输出不直接写报告或图。
5. 所有 agent 决策可审计。
6. 本地 LLM 是一等路径，DeepSeek 是同协议 provider。
7. 真实外网 smoke 手动执行，CI 使用 fake providers / fixtures。

## 推荐提交拆分

1. `add agent run state planner specs`
2. `add evidence candidate normalizer`
3. `add global agent runtime`
4. `migrate finrisk to primary agent workflow`
5. `migrate supply chain to primary agent workflow`
6. `connect graph browser memory agent loop`
7. `add agent trace api ui review contracts`
8. `add agent evaluation golden cases`

## Done Definition

V21 完成后应支持：

- 用户 goal 进入 `AgentRunState`。
- Agent planner 生成 subgoals。
- 每个 subgoal 可选择工具、产生 trace、生成 evidence candidates。
- Workflow validators 决定哪些候选进入正式 state。
- Agent 能根据 evidence sufficiency 决定继续、停止、fallback 或 human review。
- UI/API 能展示 timeline、tool calls、candidate evidence、uncertainty。
- Golden cases 能衡量 agent 决策质量。
- `uv run pytest -q` 通过。
