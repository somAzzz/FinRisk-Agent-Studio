# Step 21 - LLM-driven Agent System Closure Roadmap

## 背景

V20 已经把 FinText-LLM 从“代码直接调用工具”推进到“LLM 可通过统一 ToolCatalog 调用受控工具”：

- DeepSeek 与本地 OpenAI-compatible LLM 共用 tool loop。
- 本地 LLM 支持 `native` / `json_fallback` / `auto`。
- `ToolCatalog` 暴露 web、SEC、transcript、financial metrics、XBRL、graph read、browser explore 等工具。
- `ToolExecutionEvent` / `ToolLoopTrace` 已可审计工具调用。
- FinRisk `MarketExplorerStep` 支持 LLM primary。
- Supply Chain supplier discovery 支持 LLM shadow。
- `src/pipelines/llm_tool_research.py` 可运行真实 research smoke。

但当前系统仍更接近“带 LLM tool loop 的 workflow”，还不是完整的 LLM-driven agent system。关键差距是：

1. 没有全局 planner 和统一 `AgentRunState`。
2. workflow 顺序仍主要由 deterministic code 固定。
3. 工具结果尚未统一进入 `EvidenceCandidate` normalizer。
4. LLM final answer 还没有稳定结构化行动/结论协议。
5. Graph / browser / memory 工具已存在，但还没有形成 reasoning closed loop。
6. API/UI 尚未完整展示 agent timeline、tool traces、candidate evidence 和 human review。
7. evaluation 还缺专门衡量 agent 决策质量的 golden cases。

## V21 目标

V21 的目标是补齐从 V20 tool loop 到完整 agent system 的最后一层：

```text
User goal
  -> Agent planner
  -> AgentRunState / subgoal queue
  -> LLM chooses read tools
  -> Backend validates and executes tools
  -> EvidenceCandidate normalizer
  -> Quality / grounding / entity guards
  -> Deterministic workflow write gates
  -> Agent decides next subgoal or stop
  -> Trace / API / UI / human review
```

V21 不把系统改成无约束聊天机器人。它仍然是 evidence-first financial research system：

- LLM 负责规划、选择工具、提出候选结论、声明不确定性。
- 后端负责工具执行、安全边界、schema validation、evidence normalization。
- workflow 负责写状态、写图、生成报告、quality gates。
- human review 负责高风险或证据不足结论的最终确认。

## 非目标

V21 不做：

- 让 LLM 直接写 Neo4j、SQLite、文件、配置或 `.env`。
- 让 LLM 直接执行低层 browser `click` / `type` / `scroll`。
- 用 LangGraph 等大框架重写已有 workflow。
- 把 deterministic validators、risk scoring、graph write gates 删除。
- 把真实外网调用作为 CI 必需项。

## 新增 Specs

细化规格保存在：

```text
docs/specs/v21-llm-driven-agent-system/
```

执行顺序：

1. `00-index.md`
2. `01-agent-run-state-and-planner.md`
3. `02-unified-evidence-candidate-normalizer.md`
4. `03-global-agent-runtime-and-subgoal-loop.md`
5. `04-finrisk-primary-agent-workflow.md`
6. `05-supply-chain-primary-agent-workflow.md`
7. `06-graph-browser-and-memory-closed-loop.md`
8. `07-api-ui-trace-and-human-review.md`
9. `08-evaluation-golden-cases-and-acceptance.md`

## Milestones

### Milestone 1 - Agent State and Planner

新增全局 agent 状态与 planner schema：

- `AgentRunState`
- `AgentSubgoal`
- `AgentDecision`
- `AgentStopReason`
- `AgentRunTrace`

完成后，系统可以把用户目标拆成可审计 subgoals，并记录每次 LLM 决策。

### Milestone 2 - Unified Evidence Candidate Normalizer

新增统一证据候选层：

```text
ToolExecutionEvent
  -> EvidenceCandidate
  -> Source quality / grounding / entity binding
  -> workflow-specific evidence
```

完成后，FinRisk、Supply Chain、Graph、Browser 不再各自临时解析工具输出。

### Milestone 3 - Global Agent Runtime

在 `LLMToolAgentRuntime` 上方新增全局 agent runtime：

- planner loop
- subgoal queue
- tool-loop invocation
- evidence candidate ingestion
- budget / stop condition
- fallback / review decision

完成后，agent 能持续推进复杂任务，而不是只执行单次 research loop。

### Milestone 4 - FinRisk Primary Agent Workflow

把 FinRisk 从局部 LLM primary market exploration 推进到 agent-level primary workflow：

- filing / market / transcript / financial / graph 子目标由 planner 选择。
- evidence normalizer 决定哪些内容进入 state。
- report 只消费已通过 guardrail 的 evidence。

### Milestone 5 - Supply Chain Primary Agent Workflow

把 Supply Chain 从 supplier discovery shadow 推进到 evidence-gated primary workflow：

- LLM 生成 query 和候选 supplier/customer/component。
- validator 决定是否写 edge。
- recursive expansion 使用 graph context 和 evidence candidate。

### Milestone 6 - Graph, Browser, and Memory Closed Loop

让 graph read、browser explore、memory/context pack 进入 agent 闭环：

- Graph query result 可生成 graph evidence candidate。
- Browser findings 可进入 evidence normalizer。
- Memory/context 只读进入 planner，不由 LLM 直接写。

### Milestone 7 - API/UI Trace and Human Review

暴露 agent run：

- start / get / list agent runs。
- timeline / decisions / tool calls / candidates / final report。
- human review queue。
- trace JSON download。

### Milestone 8 - Agent Evaluation Golden Cases

新增 agent 决策质量评估：

- 是否选择正确工具。
- 是否过度搜索。
- 是否把 snippet 当强证据。
- 是否在证据不足时进入 review / fallback。
- 是否遵守 no-write boundary。

## 完成定义

V21 完成时，系统应满足：

1. 用户目标先进入 `AgentRunState`，而不是直接进入固定 workflow。
2. Agent 能规划 subgoals，并根据工具结果决定继续、停止、fallback 或 human review。
3. 所有 LLM 工具结果先进入 `EvidenceCandidate`，再进入 workflow state。
4. FinRisk 至少支持 agent primary path。
5. Supply Chain 至少支持 evidence-gated agent primary supplier discovery。
6. Graph/browser/memory 都通过高层 read-only wrappers 进入 agent loop。
7. API/UI 可以展示 agent timeline、tool calls、candidate evidence 和 uncertainty。
8. Golden cases 覆盖 agent 决策质量。
9. 全量测试通过：

```bash
uv run pytest -q
```

真实 smoke：

```bash
uv run python -m src.pipelines.llm_tool_research \
  --provider deepseek \
  --tools finrisk_market \
  --query "Find evidence about Apple's supply chain risk and distinguish evidence, inference, and uncertainty."
```
