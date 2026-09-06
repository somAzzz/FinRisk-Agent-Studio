# Chapter 4：用程序化 Workflow 和 Pydantic Graph 组织模型任务

> 当前实现导读。FinRisk 的模型负责抽取、研究、计划和有限动作选择；Python workflow 决定固定
> 顺序、状态转换、预算、质量门禁、存储和最终报告。

## 本章结果

完成本章后，你应能解释：

- 为什么 Agent 不应该互相隐式调用；
- FinRisk、Supply Chain 和 Global Agent Graph 的不同用途；
- typed clients 如何把模型任务嵌入领域 step；
- 哪些步骤刻意保持确定性；
- API、CLI 和后台任务如何共享同一组核心边界。

## 当前文件地图

| 文件 | 当前职责 |
| --- | --- |
| `src/workflows/finrisk_workflow.py` | FinRisk 公共入口、默认步骤和 CLI |
| `src/ai/graphs/finrisk.py` | FinRisk 固定顺序 Graph |
| `src/supply_chain/workflow.py` | Supply Chain 公共入口和 step composition |
| `src/ai/graphs/supply_chain.py` | Supply Chain 九步 Graph |
| `src/agents/global_runtime.py` | Global Agent 同步 facade |
| `src/ai/graphs/global_agent.py` | planner/subgoal 动态状态机 |
| `src/workflows/steps/` | FinRisk 各领域步骤 |
| `src/supply_chain/steps/` | Supply Chain 各领域步骤 |
| `src/ai/structured_clients.py` | model task 到 step protocol 的 typed adapters |

## 4.1：选择控制权

FinRisk 同时使用三类编排方式：

| 方式 | 谁控制下一步 | 用途 |
| --- | --- | --- |
| 固定 programmatic workflow | Python | 产品主流程、质量门禁、确定性输出 |
| Pydantic Graph decision route | Python 状态机 + typed planner decision | 开放式 global research subgoals |
| Agent tool loop | 模型在受限 toolset 内 | 单个 research/browser subgoal |

模型不能决定跳过 evidence normalization、risk scoring、quality gate 或 report evaluation。

## 4.2：FinRisk 九步 Graph

当前默认顺序：

```text
company_resolver
  -> filing_risk_extractor
  -> market_explorer
  -> evidence_normalizer
  -> risk_scorer
  -> lifecycle_classifier
  -> graph_reasoner
  -> report_generator
  -> evaluator
```

`run_finrisk_workflow()` 是稳定公共入口，内部委托 `run_finrisk_graph()`。Graph 保持原有
`FinRiskWorkflowState`，每个 node 仍调用现有 step object。

失败后的后续 step 会生成 skipped trace；启用 quality gate 时，critical blocker 可以终止，
非关键 market/graph blocker 可以降级继续。

这是一种保守迁移：Graph 表达实际控制流，但没有为了“图化”重写成熟领域代码。

## 4.3：Supply Chain 九步 Graph

```text
product_resolver
  -> requirement_decomposer
  -> supplier_discovery
  -> evidence_normalizer
  -> graph_builder
  -> node_profile
  -> sankey_builder
  -> evaluator
  -> graph_projection
```

initialize 和 finish 节点负责既有 run-store 写入。模型任务通过
`PydanticAISupplyChainClient` 进入 requirement、supplier relation 和 node profile 等 step；
evidence normalization、confirmed edge、Sankey 和 graph projection 仍由领域层决定。

## 4.4：Global Agent 动态循环

Global Agent Graph 是当前最接近 agentic orchestration 的部分：

```text
initialize
  -> plan_next
  -> execute_subgoal
  -> plan_next
  -> ...
  -> finish
```

planner 输出 typed `AgentDecision`；Python graph 负责执行和停止：

- 最大 subgoal、tool call 和 wall-clock budget；
- pending subgoal 的状态转换；
- runtime failure 与 no-tool-evidence；
- tool events 到 evidence candidates 的 normalization；
- accepted evidence IDs 和 human-review items；
- stop reason 与 trace。

`GlobalAgentRuntime` 只保留同步调用合同，内部没有旧 planner while-loop。

## 4.5：模型任务如何嵌入固定 workflow

以 filing 为例：

```text
Graph node
  -> FilingRiskExtractorStep
  -> PydanticAIFilingExtractionClient
  -> filing Agent
  -> FilingRiskExtractionOutput
  -> ChunkValidation / LLMCall
  -> workflow state
  -> EvidenceNormalizerStep
  -> deterministic validators/scoring/report
```

Agent 不直接调用下一个 Agent；step/workflow 明确传递 typed data。这样可以测试每个边界，也能在
provider 不可用时选择业务降级，而不替换整个 runtime。

## 4.6：刻意保持确定性的职责

以下能力不应因“Agent 化”而改成模型输出：

- risk score 权重与计算；
- lifecycle classification；
- evidence normalization 和 source identity；
- claim grounding/source-quality gate；
- graph edge/path 验证；
- Sankey canonicalization；
- report 结构与 evidence table；
- authorization、预算扣减和发布状态。

模型可以解释或提出候选，但不能成为这些规则的唯一执行者。

## 4.7：多个 composition roots，共享一个核心

FinRisk 不是单一 CLI。入口包括 FastAPI、workflow CLI、research cycle、Supply Chain API 和
background runs。它们可以分别组装对象，但必须共享：

```text
model factory
typed Agent builders
typed client/runtime adapters
workflow/Graph entrypoints
project stores and policies
```

不能让某个 API endpoint 自己调用 provider SDK，或让 CLI 使用另一套 JSON loop。

## 4.8：练习与验收

```bash
uv run python -m pytest -q \
  tests/ai/graphs \
  tests/workflows \
  tests/supply_chain \
  tests/agents/test_global_agent_runtime.py
```

运行离线 demo：

```bash
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify current material risks." \
  --demo-mode
```

- [ ] 公共 workflow 入口委托 Graph，而不是保留平行 step loop。
- [ ] typed Agent output 在进入 report 前经过 deterministic domain layers。
- [ ] Global Agent 的动态性被预算和状态机约束。
- [ ] provider fallback 与业务 fixture/cache 降级明确区分。
- [ ] 多个产品入口没有创建多个模型 runtime。

下一章用离线测试、golden cases 和 live acceptance 分别验证架构与质量。
