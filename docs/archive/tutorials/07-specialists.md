# Chapter 7：理解 Typed Agents、Adapters 与 Pydantic Graph Cutover

> 当前实现导读。本章描述已经完成的 Pydantic AI 单一运行时，不再把 adapter 或
> `GlobalAgentRuntime` 的薄 facade 误判成第二套 LLM runtime。

## 本章结果

完成本章后，你应能解释：

- 哪些模型任务已经使用专用 typed output；
- 为什么现有业务协议前仍保留 typed client/runtime adapter；
- FinRisk、Supply Chain 和 Global Agent 三类 Graph 的状态与停止规则；
- 哪些旧组件确实已经删除，哪些名字只为持久化兼容而保留。

当前系统只有 Pydantic AI 会发起模型调用。provider 失败可以触发 fixture、缓存或确定性业务
降级，但不会切换回旧 SDK tool loop。

## 当前文件地图

| 文件 | 当前职责 |
| --- | --- |
| `src/ai/agents/research.py` | Market Research Agent 与 source-backed output validator |
| `src/ai/agents/structured.py` | filing、supplier relation、requirements、proposal、profile、planner 等 typed Agents |
| `src/ai/structured_clients.py` | 把 typed Agents 接入既有 filing/supply-chain/extraction 业务协议 |
| `src/ai/browser_client.py` | 页面摘要与有界 browser action Agent |
| `src/ai/planner_adapter.py` | 把 typed planner 接到 `AgentPlanner` 可调用边界 |
| `src/ai/runtime_adapter.py` | 把 Pydantic AI Agent 结果投影成 subgoal workflow 所需合同 |
| `src/ai/graphs/finrisk.py` | 现有 FinRisk 顺序 workflow 的 Graph 投影 |
| `src/ai/graphs/supply_chain.py` | 现有 Supply Chain 九步 workflow 的 Graph 投影 |
| `src/ai/graphs/global_agent.py` | planner → subgoal → planner 的有界状态机 |
| `src/agents/global_runtime.py` | 保持同步调用合同的薄 facade；内部执行 Global Agent Graph |

## 7.1：当前 Agent 边界

### Market Research Agent

`ResearchAgentOutput` 明确表达：

```text
status: completed | needs_review
answer
evidence[]
uncertainties[]
suggested_next_checks[]
```

每条 `ResearchEvidence` 必须带 `source_id`、HTTP(S) URL、evidence kind、摘要/quote、claim
和 0–1 confidence。validator 保证：

- 无 evidence 时不能标记 completed；
- 无 evidence 时必须说明 uncertainty；
- `source_id` 不可重复。

它没有证明 quote 一定支持 claim，也没有证明来源独立；这些仍由后续确定性质量层负责。

### Structured Agents

`src/ai/agents/structured.py` 没有使用一个通用 JSON envelope 覆盖所有任务，而是复用各领域
已经存在的 Pydantic model：

| Agent | Output |
| --- | --- |
| filing extraction | `FilingRiskExtractionOutput` |
| supplier relation | `SupplierRelationBatch` |
| requirement decomposition | `RequirementDecomposition` |
| supplier proposal | `SupplierProposalBatch` |
| node profile | `NodeProfileBatch` |
| generic extraction | `ExtractionResult` |
| planner | `AgentDecision` |

局部 validator 只保证本次输出内可确定的规则。例如 confirmed supplier relation 必须有 URL
和 quote；空 filing extraction 必须标记 `needs_review`；planner 选择的 scope/tool 必须属于
本次 deps 的可见集合。

确定性风险评分、evidence normalization、图边确认和报告渲染没有被 Agent 化。

## 7.2：为什么当前 adapters 是合理边界

旧版教程要求“不要写 adapter”过于绝对。当前这些 adapter 不会构造旧 SDK client，也不实现
第二套 tool loop；它们只做合同投影：

```text
现有同步 workflow protocol
  -> typed Agent.run(...)
  -> validated result.output
  -> 现有 domain/workflow result
```

### `structured_clients.py`

它保留调用方已经消费的业务方法，例如：

- `extract_risks_chunked()`；
- `extract_supplier_relations()`；
- `decompose_requirements()`；
- `propose_suppliers()`；
- `profile_nodes()`；
- `extract()`。

内部模型调用全部是 Pydantic AI Agent，输出验证后再投影为原业务返回类型。这样 cutover 不需要
同时重写所有 deterministic workflow。

### `runtime_adapter.py`

`PydanticAIRuntimeAdapter` 为 subgoal runtime 提供同步 `run(goal)`，内部完成：

1. 构造 scoped toolset；
2. 应用 request/tool-call limits；
3. 可选加载可信 conversation history；
4. 调用 `Agent.run()`；
5. 提取 `ToolCallPart` 和 `ToolExecutionEvent`；
6. 记录新 messages 和 usage；
7. 返回 `LLMToolRunResult`。

`run_awaitable_sync()` 在已有 event loop 中使用专用线程运行 coroutine。它是同步/异步边界，
不是 provider fallback。长期如果调用链全面 async 化，可以删除这个桥，但不是当前 v0.1 的前提。

## 7.3：Browser Agent 的特殊边界

`PydanticAIBrowserClient` 有两个 Agent：

- `summary_agent` 输出 typed `PageSummary`；
- `exploration_agent` 通过 `browser_action` 工具输出 typed `BrowserExplorationOutcome`。

真实浏览器 I/O 位于注入的 `BrowserToolSession`。Agent 只能选择 typed `BrowserAction`，不能直接
访问 Playwright。`max_steps` 同时约束 model requests 和 tool calls。

页面摘要失败时返回最多 200 字符的确定性 fallback；探索失败返回 `None`。这两个行为必须在调用方
显示为降级，不能解释为“没有风险”。

## 7.4：三类 Graph 的真实成熟度

### FinRisk Graph

`run_finrisk_graph()` 保持 `FinRiskWorkflowState` 公共合同，把现有步骤按固定顺序投影为 Graph。
当 `quality_gated=True` 时，每步通过 `run_step_with_quality_gate()`；critical step 出现 blocker
可把 workflow 标为 failed。

它目前是“一步一节点”的顺序图，不是动态模型编排器。

### Supply Chain Graph

`run_supply_chain_graph()` 投影九个固定步骤，并在 initialize/finish 使用既有 store。它同样优先
保持原 state、step 和持久化语义，而不是为采用 Graph 重写领域层。

### Global Agent Graph

这是当前真正含动态 decision route 的图：

```text
initialize -> plan_next -> execute_subgoal -> plan_next -> ... -> finish
```

它执行以下确定性限制：

- `max_subgoals`；
- `max_total_runtime_seconds`；
- `max_total_tool_calls`；
- planner 未选择工具时停止；
- subgoal 无 tool evidence 时进入 `needs_review`；
- tool events 经 `EvidenceCandidateNormalizer` 后才能成为 accepted evidence ID；
- child failure 留在 trace/fallback events。

`GlobalAgentRuntime.run()` 只是同步 facade，内部直接调用 `run_global_agent_graph()`。

## 7.5：并行不是默认优化

当前 FinRisk 和 Supply Chain Graph 都是顺序执行。`src/ai/graphs/parallel_policy.py` 用
`NodeAccess(reads, writes)` 检查 read-after-write、write-after-read 和 shared-write 冲突。

现有 filing extraction 与 market exploration 不能直接并行，因为 market 会读取
`filing_risks`，两者还会写共享 `llm_log`。只有先引入 branch-local buffer 和确定性 reducer，
才应启用并行。

## 7.6：cutover 的当前证据

已经删除的生产路径包括：

- `src/llm/` 直接 clients；
- 自定义 `LLMToolAgentRuntime`；
- 独立 OpenAI tool-call/JSON fallback loop；
- 运行时 `legacy/shadow/primary` 选择开关。

仍然出现的历史字符串不代表双 runtime：

- `StoredAgentRuntimeMode` 保留旧数据库值可读；
- `AgentRunState.runtime_mode` 默认值兼容旧序列化数据；
- source-gate 测试会用旧类名作为禁止项；
- API 新 run 的真实 mode 来自唯一的 `AgentRuntimeMode = Literal["pydantic_ai"]`。

## 7.7：测试与验收

```bash
uv run python -m pytest -q \
  tests/ai/test_research_agent.py \
  tests/ai/test_structured_agents.py \
  tests/ai/test_structured_clients.py \
  tests/ai/test_browser_client.py \
  tests/ai/test_runtime_adapter.py \
  tests/ai/test_planner_adapter.py \
  tests/ai/graphs

uv run python -m pytest -q \
  tests/agents/test_global_agent_runtime.py \
  tests/pipelines/test_llm_tool_research.py \
  tests/test_import_all_modules.py
```

人工检查：

```bash
find src/llm -type f 2>/dev/null
rg -n "chat\.completions|LLMToolAgentRuntime" src
```

第一条应为空或目录不存在。第二条不应命中生产调用代码。

- [ ] typed output failure 不会退回手工 JSON repair。
- [ ] adapters 只投影合同，不选择第二个 provider/runtime。
- [ ] Graph 不绕过现有 deterministic quality layer。
- [ ] 无工具证据的 subgoal 会进入 review，而不是伪造成功。
- [ ] 能解释为什么当前顺序 Graph 没有盲目开启并行。

下一章学习这些 Agent 如何接入同步调用方、消息持久化、conversation resume 和流事件。
