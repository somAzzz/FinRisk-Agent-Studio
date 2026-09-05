# Chapter 7：Typed Specialists、Pydantic Graph 与正式 Cutover

## 本章结果

本章把生产模型调用全部迁移到专用 typed Agents，以 Pydantic Graph 表达有状态编排，
然后删除旧 SDK clients、旧 tool loop、旧 runtime 和 generic JSON 恢复逻辑。

完成后系统只有一套 LLM runtime：Pydantic AI。失败时可以走缓存、fixture 或确定性业务
降级，但不能切回另一套模型循环。

前置条件：Chapter 6 的 typed smoke、权限和 tool execution tests 已通过；不得跳过新
边界的独立验证直接删除旧 runtime。

## 先划清 Agent 边界

适合 typed Agent 的职责：

- 从 filing 文本提取风险事实；
- 搜索并整理当前市场证据；
- 生成候选供应链关系；
- 解释工具已经返回的 verified graph paths；
- 在有界候选集合中选择下一研究动作。

不应 Agent 化的职责：

- `RiskAgent` 的确定性风险聚合；
- `CriticAgent` 的规则式清理；
- `ReportAgent` 的确定性报告组装；
- evidence normalization、claim binding、source quality；
- graph path 检索、边存在性与评分；
- authorization、预算扣减与发布门禁。

判断标准不是“模型能不能做”，而是该职责是否需要可重复、可证明、可审计。

## 文件变更总览

### 新建文件

| 文件 | 必须实现的职责 | 接替的旧职责 |
| --- | --- | --- |
| `src/ai/agents/__init__.py` | 只导出正式 specialist builders 与 output models | 统一新 Agent 入口 |
| `src/ai/agents/models.py` | finding、evidence reference、uncertainty、status 等共享模型 | 替代自由文本/任意 dict Agent 输出 |
| `src/ai/agents/research.py` | Filing、Market、Graph specialist builders 与 validators | 替代通用“一个 Agent 做所有研究” |
| `src/ai/agents/structured.py` | extraction、planner、supply-chain 专用 Agents | 替代 generic JSON prompt/client 与手工 repair |
| `src/ai/run_service.py` | 统一执行 Agent、注入 deps/limits/history、记录 messages/usage | 接替旧 runtime 的 application-level 生命周期，不模仿旧 API |
| `src/ai/graphs/__init__.py` | 导出正式 graph entrypoints | workflow 编排统一入口 |
| `src/ai/graphs/reducers.py` | 并行节点合并的确定性 reducer | 替代隐式 list mutation/last-write-wins |
| `src/ai/graphs/finrisk.py` | FinRisk workflow 的节点、边、失败与停止条件 | 替代 `finrisk_workflow.py` 的手写 step loop |
| `src/ai/graphs/supply_chain.py` | supply-chain workflow graph | 替代 `supply_chain/workflow.py` 的手写 step loop |
| `src/ai/graphs/global_agent.py` | planner → subgoal → planner 的有界状态机 | 替代 `global_runtime.py` 内手写 while-loop |
| `src/ai/browser_client.py` | 浏览器动作选择与页面摘要的 typed Agent 边界 | 替代 Browser Explorer 的直接 SDK completion |

### 新建测试

```text
tests/ai/
  test_agent_models.py
  test_research_agents.py
  test_structured_agents.py
  test_run_service.py
  test_browser_client.py
  graphs/
    __init__.py
    test_reducers.py
    test_finrisk_graph.py
    test_supply_chain_graph.py
    test_global_agent_graph.py
tests/test_import_all_modules.py
```

### 修改生产调用方

| 文件/目录 | 修改目标 | 新调用关系 |
| --- | --- | --- |
| `src/workflows/steps/filing_risk_extractor.py` | 删除任意 `parse`/`complete` client 分支 | 调用 filing typed Agent，失败转为明确 workflow 状态 |
| `src/workflows/steps/market_explorer_step.py` | 删除直接 SDK/旧 runtime | 调用 Market Researcher；只有模型不可用时走确定性搜索降级 |
| `src/workflows/finrisk_workflow.py` | 删除默认手写 step loop | 成为 `run_finrisk_graph` 的薄入口 |
| `src/supply_chain/llm.py`、`llm_extraction.py` | 删除 generic JSON 与字符串 completion | 调用专用 supply-chain output models/Agents |
| `src/supply_chain/steps/*.py` | 注入 typed Agent runner，不做 JSON 修复 | domain step 消费 validated model |
| `src/supply_chain/workflow.py` | 删除默认手写 loop | 成为 `run_supply_chain_graph` 的薄入口 |
| `src/browser/explorer.py` | 页面摘要和动作选择改用 `browser_client` | 浏览器 I/O 与模型决策分离 |
| `src/agents/extraction_agent.py` | 只接受 typed extraction boundary | 删除任意 client duck typing |
| `src/agents/global_runtime.py` | 只保留薄 facade 或直接由调用方使用 graph | 不再拥有 planner loop |
| `src/pipelines/llm_tool_research.py` | 使用 `run_service` | 不再构造旧 runtime |
| `src/api/agent_runs.py` | composition root 创建 model/deps/toolsets/run service | API 不感知 provider SDK |
| `src/tools/contracts.py`、`src/tools/catalog.py` | 删除只为旧 loop 存在的 `parameters`/`openai_schema`；保留仍有非 LLM 用途的 backend 与 policy metadata | typed 函数签名成为唯一模型 schema 来源 |
| `tests/tools/test_tool_contracts.py` | 删除旧 OpenAI schema 断言，改测 backend/policy 合同 | 防止双 schema 回归 |
| `pyproject.toml`、`uv.lock` | 旧 clients 删除后移除顶层 `openai` 依赖并重新锁定 | OpenAI SDK 只允许作为 Pydantic AI provider extra 的传递依赖 |

### 完成 cutover 后删除

```text
src/agents/runtime.py
src/agents/llm_runtime.py
src/llm/client.py
src/llm/deepseek_client.py
src/llm/sglang_client.py
src/llm/tool_loop.py
src/tools/router.py
tests/agents/test_runtime.py
tests/agents/test_llm_runtime.py
tests/llm/test_client.py
tests/llm/test_deepseek_client.py
tests/llm/test_tool_loop.py
tests/llm/test_tool_loop_fallback.py
```

如果整个 `src/llm/` 删除后为空，一并删除包目录。若 `src/tools/router.py` 仍有非 LLM
调用方，先把该确定性职责迁到命名准确的 service，再删除旧 router；不要为了满足清单
盲删仍在使用的领域逻辑。

## 7.1：先设计 output models

不要先写 prompt。先在 `src/ai/agents/models.py` 确定模型边界。

共享研究输出至少表达：

```text
Finding
  kind
  statement
  evidence_ids[]
  confidence (0..1)
  uncertainty

SpecialistResult
  status: completed | needs_review | failed
  findings[]
  missing_information[]
  suggested_next_checks[]
```

结构规则：

- 所有模型 `extra="forbid"`；
- material finding 至少一个非空 evidence ID；
- evidence IDs 去重；
- `completed` 必须至少有一个 grounded finding；
- 没有 evidence 时只能 `needs_review` 或 `failed`，且说明原因；
- confidence 是模型自报置信度，不等于 source trust score；
- graph finding 只能引用 graph tool 返回的 path/evidence ID。

以下规则不能只靠 model validator 假装完成：evidence 是否存在、quote 是否支持 claim、
来源是否独立、graph edge 是否真实。这些由输出 validator 或下游领域层查询实际数据。

## 7.2：三个窄 specialists

### Filing Researcher

- toolsets：filing + financial；
- 输出：披露事实、解释、不确定性分开；
- 优先 primary filing/XBRL evidence；
- 不提供投资建议；
- 不允许 browser、market search 或 graph tool。

### Market Researcher

- toolsets：market；browser 只有明确权限时额外注入；
- search snippet 只能作为候选，重要结论需 fetch 后引用；
- 记录来源 URL、时间点、source ID；
- 没有可用来源时输出 `needs_review`；
- 不允许 filing 全文、financial 或 graph tool。

### Graph Interpreter

- toolsets：graph；
- 只解释工具返回的 verified paths，不能创建 edge；
- empty path 表示 `missing_information`，不是“关系不存在”；
- 输出 evidence ID 必须来自本次 path payload；
- 不允许 web/browser/write tool。

每个 builder 都必须显式传入 `Model` 和对应 toolset，并声明 `deps_type`、typed
`output_type`、稳定 name 与 output validator。不要在模块 import 时创建全局 Agent。

## 7.3：专用 structured Agents

`src/ai/agents/structured.py` 为不同模型任务定义不同 output：

- filing risk extraction；
- requirement decomposition；
- supplier proposal；
- supplier relation extraction；
- node profile；
- planner decision。

不得用一个 `dict[str, Any]` 或 `GenericJSONResult` 覆盖所有任务。每个 schema 只包含
下游真正消费的字段，并用 validator 表达局部不变量。

删除以下行为：

- 从 Markdown code fence 抠 JSON；
- JSON 失败后替换引号/括号再解析；
- typed output 失败后调用旧 `complete()`；
- 通过 `hasattr(client, "parse")` 接受任意 client；
- 用空 list 抹掉 provider/validation failure。

失败应成为显式状态或异常，由 workflow 决定 retry、fallback 或 review。

## 7.4：区分三种编排

### Programmatic handoff

固定顺序、可预测成本：

```text
Filing Agent -> deterministic normalization -> Market Agent -> quality layer
```

适合产品主 workflow。顺序由 Python 控制，模型不决定是否跳过质量层。

### Agent delegation

coordinator 将 specialist 暴露为窄工具，由模型选择调用对象。适合开放式研究入口，但
必须给 child 自包含任务、独立限制和结构化失败。child output 仍进入领域质量层。

### Pydantic Graph

跨步骤存在业务状态、并行 join、重试或明确停止条件时使用。Graph 节点不应只是把所有
函数机械包一层；每个节点应代表可检查的状态转换。

Chapter 8 的 Harness SubAgents/DynamicWorkflow 是第四种选择，不要在本章提前依赖。

## 7.5：实现 Pydantic Graph

Graph state 必须由 typed model/dataclass 表达，并至少包含 run identity、业务输入、
中间产物、budget、review items、errors 和 trace correlation IDs。

### FinRisk graph

建议节点：resolve company → fetch/normalize evidence → typed extraction → deterministic
risk scoring → graph reasoning → quality gate → report。LLM 节点和确定性节点在图中要能
一眼区分。

### Supply-chain graph

建议节点：resolve product → decompose requirements → discover candidate suppliers → normalize
evidence → build/validate graph → project/report。并行分支使用显式 reducer，禁止共享 list
并发 mutation。

### Global Agent graph

表达 `plan_next`、`execute_subgoal`、`finish` 三类状态转换，并强制：

- 最大 planner decisions；
- 最大 subgoals/tool calls/tokens；
- 没有进展时停止；
- child failure 留在 trace；
- missing evidence 进入 review；
- 最终结果不绕过 evidence normalization。

## 7.6：run service，而不是旧接口 adapter

`src/ai/run_service.py` 应负责：

- 接受显式 model、Agent、deps 和 limits；
- 从可信 message store 加载 history；
- 调用 `agent.run()`；
- 原子记录新 messages、usage、latency 和状态；
- 返回新的 application result contract。

不要让它复制 `LLMToolAgentRuntime.run(goal) -> old result` 的全部形状。先列出当前 API、
workflow 和持久化真正需要的字段，再定义新合同并一次性迁移调用方。同步入口如确实需要，
只能是薄边界，不能在已有 event loop 中偷偷 `asyncio.run()`。

## 7.7：逐路径切换并立即删除旧分支

推荐顺序：

1. filing extraction；
2. market research；
3. browser decision；
4. supply-chain structured tasks；
5. global research/planner；
6. FinRisk/Supply-chain graph entrypoints；
7. API、CLI、background task composition roots。

每迁移一条路径，立即删除该路径的旧 `parse`/`complete`/runtime fallback 和对应测试。
全部完成后删除旧文件清单，再运行仓库级 source gate。不要保留“以后可能回滚”的死代码；
回滚依赖 Git/deployment revision。

## 7.8：测试矩阵

| 测试组 | 必须证明 |
| --- | --- |
| agent model tests | extra fields、grounding/status、duplicate IDs、confidence 边界 |
| specialist tests | 工具隔离、empty evidence、graph empty path、output retry 边界 |
| run service tests | history 隔离、usage 归集、record idempotency、failure classification |
| graph tests | 节点顺序、并行 reducer、预算停止、异常路径、quality gate 不可绕过 |
| browser tests | typed action、步骤上限、tool permission、页面内容不直接成为可信指令 |
| workflow/API tests | 新合同端到端生效；无旧 runtime 构造 |
| source/import gate | 旧文件、旧类名、direct `chat.completions`、generic repair 不再存在 |

单元测试使用 `TestModel` / `FunctionModel` 和 fake services；live provider 只在独立的
acceptance script 中运行，并显式标记 integration。

## 本章验收

```bash
uv run ruff check src tests
uv run pytest -q
uv run python -m src.ai.smoke
```

额外检查：

```bash
rg -n "chat\.completions|LLMToolAgentRuntime|AgentRuntimeMode|repair_json" src
find src/llm -type f 2>/dev/null
```

期望第一条没有生产命中；第二条为空或目录不存在。若某个词是领域文档中的正常文本，
在 source gate 中精确限定路径，不要简单忽略整个目录。

- [ ] 所有模型任务都有专用 typed output。
- [ ] 每个 specialist 只有窄 toolset。
- [ ] Pydantic Graph 表达业务状态与停止条件。
- [ ] 确定性 Risk/Critic/Report/validators 未被 Agent 替换。
- [ ] API、CLI、workflow 都已切换。
- [ ] 旧 runtime、generic clients 和手工 JSON repair 已删除。
- [ ] provider 失败只触发明确业务降级，不触发第二套 LLM runtime。

本章建议提交：

```text
ch07: cut over to typed specialist agents and graphs
```
