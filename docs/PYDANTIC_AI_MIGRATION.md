# Pydantic AI Agent 重构与迁移执行方案

- 状态：提案，尚未开始实施
- 最后更新：2026-08-23
- 目标版本：v0.2
- 适用范围：后端 Agent、LLM、Tool、Workflow、运行存储、观测与相关测试

## 1. 文档目的

本文定义 FinRisk Agent Studio 使用 Pydantic AI 重构现有 Agent 基础设施的目标架构、实施顺序、兼容策略、测试方法和验收门禁。它是工程执行规范，不代替：

- [项目状态](STATUS.md)：只记录已经完成并验证的事实；
- [路线图](ROADMAP.md)：只记录版本目标和工作包；
- [v0.1 规格](specs/v0.1.md)：继续定义当前已发布合同；
- [系统架构](ARCHITECTURE.md)：在迁移完成并成为主路径后再更新为最终架构。

本迁移不是把所有业务逻辑改造成自主 Agent，而是收敛当前重复的 Agent 运行时，同时保留金融研究中的确定性计算、证据门禁和安全边界。

## 2. 决策摘要

采用“Pydantic AI Agent + Pydantic Graph/确定性工作流”的混合架构：

```text
FastAPI / CLI
      │
      ▼
Application Service
      │
      ▼
Pydantic Graph / Deterministic Workflow
      │
      ├── Deterministic Nodes
      │   ├── Company/Ticker Resolution
      │   ├── Evidence Normalization
      │   ├── Financial/Risk Scoring
      │   ├── Graph/Sankey Projection
      │   └── Guardrails and Evaluation
      │
      └── Pydantic AI Agent Nodes
          ├── Filing Extraction Agent
          ├── Market Research Agent
          ├── Supply Chain Discovery Agent
          ├── Graph Reasoning Agent
          └── Report Agent
                  │
                  ▼
             Typed Toolsets
                  │
                  ▼
       SEC / Search / Browser / Graph / Stores
```

核心约束：

1. Pydantic AI 负责模型交互、工具调用、结构化输出、模型侧重试、usage 和消息历史。
2. Pydantic Graph 或现有 workflow 负责确定性流程、分支、并行和恢复边界。
3. 现有 Pydantic 模型继续作为 API、存储和领域合同。
4. 现有 evaluator、guardrail、证据绑定和金融安全检查继续拥有最终裁决权。
5. Agent 可以提出候选事实、关系和报告，但不能绕过服务端验证直接确认图边或执行写操作。
6. 迁移必须通过 `plan_only → shadow → primary → remove_legacy` 逐级推进，不允许一次性替换。

## 3. 当前基线与问题

### 3.1 已确认基线

- Python：`>=3.12,<3.13`。
- Pydantic：当前锁定为 `2.12.5`。
- FastAPI：当前锁定为 `0.132.0`。
- 当前环境未安装 `pydantic-ai`。
- 源码约有 184 个直接继承 `BaseModel` 的模型，分布在约 58 个文件。
- 当前测试发现基线为 979 个测试。
- 本方案编写前执行的 Agent/Tool/Agent Workflow/API 定向回归为 `115 passed`。
- `STATUS.md` 中最近一次发布基线为 `972 passed, 7 skipped`；实施开始前必须重新生成完整基线。

### 3.2 重复的运行时职责

当前存在三套部分重叠的运行机制：

| 当前组件 | 主要职责 | 迁移目标 |
| --- | --- | --- |
| `src/agents/runtime.py::AgentRuntime` | 规则 planner 与旧 Agent 调度 | 冻结后退役 |
| `src/agents/llm_runtime.py::LLMToolAgentRuntime` | 单次 LLM 工具循环 | 由 Pydantic AI `Agent` 替代 |
| `src/agents/global_runtime.py::GlobalAgentRuntime` | subgoal、预算、证据候选、人工复核 | 先保留为兼容层，后收敛为 application service/graph |
| `src/llm/tool_loop.py` | native tool loop、JSON fallback、审计与预算 | 由 Pydantic AI model/tool/output 机制替代 |
| `src/tools/contracts.py` | 手写 OpenAI tool schema 与执行 envelope | 迁移为 typed function toolset |
| 多个 `_extract_json`/`_coerce_*` | 容错提取模型 JSON | 迁移为 typed output + output retry |

### 3.3 当前最重要的架构缺口

1. `primary` Agent wrapper 当前仍沿用 deterministic workflow 的最终输出，与 `shadow` 没有真正的主路径差异。
2. 工具 schema、工具执行、结果截断、审计和预算由项目重复实现。
3. LLM 输出在不同模块中使用不同的 JSON 容错策略，失败语义不统一。
4. `GlobalAgentRuntime.run()` 为同步接口，但 FastAPI 和主工作流是异步接口。
5. Agent 业务状态、模型消息历史、LLM audit trace 混合在一起，恢复语义不明确。
6. `max_tool_rounds` 同时承担循环、重试和预算含义，无法精确区分 transport、tool、output 和 workflow retry。

## 4. 范围与非目标

### 4.1 本次迁移范围

- Pydantic AI provider/model factory；
- typed dependencies；
- typed toolsets；
- Research、Extraction、Planner、Graph/Supply Chain、Report Agent；
- 结构化输出与 output validator；
- usage、retry 和 timeout；
- Agent message history、run/conversation correlation；
- 与现有 `AgentRunState`、timeline、trace 和 human review 的兼容投影；
- FinRisk/Supply Chain 的 workflow/graph 集成；
- 单元、合同、shadow、live 和 eval 验收。

### 4.2 明确不在本次迁移中重写

- ticker、CIK 和公司解析；
- SEC、EDGAR、XBRL 抓取及财务计算；
- 风险评分和估值公式；
- Evidence normalization；
- SSRF、URL allow/deny、脱敏和 API 鉴权；
- SQLite/Neo4j 存储实现本身；
- Sankey 构建算法；
- schema、grounding、source quality、financial safety 和 graph guardrail；
- 前端产品信息架构；
- 自动交易或投资建议。

### 4.3 不采用的实现方式

- 不建立一个拥有所有权限的全自主 supervisor；
- 不让 Agent 直接把 candidate edge 标记为 confirmed；
- 不用 prompt 代替服务端鉴权和参数验证；
- 不在第一阶段引入 Temporal、DBOS、Restate 等 durable runtime；
- 不在第一阶段同时切换 Pydantic AI、Pydantic Graph、provider API 和持久化格式；
- 不以删除旧代码作为先决条件，先建立可比较的新路径。

## 5. 目标代码结构

建议新增：

```text
src/ai/
├── __init__.py
├── deps.py                 Typed Agent dependencies
├── model_factory.py        Provider/model/profile construction
├── usage.py                Budget → UsageLimits mapping
├── recorder.py             Pydantic AI events → project trace
├── runtime_adapter.py      Compatibility adapter for GlobalAgentRuntime
├── outputs.py              Cross-agent output contracts
├── validators.py           Output validators and ModelRetry mapping
├── toolsets/
│   ├── __init__.py
│   ├── common.py
│   ├── company_research.py
│   ├── market_research.py
│   └── supply_chain.py
└── agents/
    ├── __init__.py
    ├── planner.py
    ├── research.py
    ├── extraction.py
    ├── graph_reasoning.py
    ├── supply_chain.py
    └── report.py
```

在 Pydantic Graph 阶段再新增：

```text
src/ai/graphs/
├── __init__.py
├── finrisk.py
├── supply_chain.py
├── state.py
└── reducers.py
```

旧目录在迁移期继续存在。删除条件见第 16 节。

## 6. 依赖和 Provider 设计

### 6.1 依赖声明

第一阶段建议在 `pyproject.toml` 显式声明：

```toml
"pydantic>=2.12,<3",
"pydantic-ai-slim[openai]>=2,<3",
```

要求：

- 更新 `uv.lock`；
- CI 继续使用 `uv sync --frozen`；
- 不依赖 FastAPI 间接安装 Pydantic；
- Pydantic AI 跨大版本升级必须单独 PR，不与业务改动混合。

### 6.2 Model factory

`src/ai/model_factory.py` 只负责构造 Pydantic AI `Model`，不得包含业务 prompt 或工具。

必须支持：

| 项目 provider | Pydantic AI 适配 | 首选协议 |
| --- | --- | --- |
| DeepSeek | dedicated provider 或 `OpenAIChatModel` | Chat Completions |
| SGLang | `OpenAIChatModel` + custom `OpenAIProvider` | Chat Completions |
| vLLM | `OpenAIChatModel` + custom `OpenAIProvider` | Chat Completions |

必须配置或探测：

- `base_url`、`api_key`、`model_name`；
- 是否支持 native tools；
- 是否支持 JSON schema output；
- 是否支持 strict tool definitions；
- 是否只接受一个 leading system message；
- `max_tokens` 与 `max_completion_tokens` 差异；
- timeout、transport retry 和连接池生命周期。

第一阶段不切换到 OpenAI Responses API，避免与 SGLang/vLLM 兼容性迁移耦合。

### 6.3 Provider 验收矩阵

| 场景 | DeepSeek | SGLang | vLLM |
| --- | --- | --- | --- |
| plain text | 必测 | 必测 | 必测 |
| function tool | 必测 | 必测 | 必测 |
| structured output | 必测 | 必测 | 必测 |
| invalid tool args retry | 必测 | 必测 | 必测 |
| output validation retry | 必测 | 必测 | 必测 |
| timeout/429/5xx | mock 必测，live 可选 | mock 必测 | mock 必测 |
| streaming events | 后续阶段 | 后续阶段 | 后续阶段 |

## 7. Typed dependencies

新增一个 dataclass 依赖容器，不把可变 workflow state 整体暴露给工具：

```python
@dataclass
class AgentDeps:
    run_id: str
    workflow_kind: AgentWorkflowKind
    settings: Settings
    search_router: SearchRouter
    filing_fetcher: FilingFetcher
    transcript_provider: TranscriptProvider
    graph_backend: GraphBackend
    context_builder: AgentContextBuilder | None
    evidence_sink: EvidenceSink
    run_store: AgentRunStore
    subject: AgentSubject
    permissions: AgentPermissions
```

实施要求：

1. 外部连接由 application service 创建并管理生命周期。
2. Agent 全局实例只保存静态配置，不保存每次运行状态。
3. `run_id`、subject、权限和 provider client 在 `deps` 中按运行传入。
4. 工具只能通过 `ctx.deps` 访问服务，不得读取模块级可变全局变量。
5. secret 不进入模型 prompt、tool result 或可下载 trace。
6. 测试通过替换 deps 注入 fake，不再依赖大范围 monkeypatch。

## 8. Toolset 迁移设计

### 8.1 现有工具分组

当前 13 个工具按业务域迁移：

| Toolset | 工具 |
| --- | --- |
| Company Research | `sec_list_filings`、`sec_fetch_filing`、`transcript_lookup`、`management_snapshot_lookup`、`financial_metrics_lookup`、`xbrl_fact_lookup`、`financial_snapshot_lookup` |
| Market Research | `web_search`、`web_fetch`、`search_and_fetch`、`browser_explore`、`graph_query`、`graph_path_search` |
| Supply Chain | 从 filing、transcript、financial、web、graph 中按 scope 组合，不复制实现 |

### 8.2 参数和返回合同

每个工具必须具有：

- 完整 Python 类型；
- 有业务意义的 docstring；
- `Field` 约束或 Pydantic 参数模型；
- typed return model；
- 可序列化的稳定 envelope；
- `risk_level`、`scopes`、`evidence_kind`、`max_result_chars` metadata。

建议统一返回：

```python
class ToolEnvelope[T](BaseModel):
    tool: str
    status: Literal["success", "failed"]
    data: T | None = None
    evidence_kind: EvidenceKind
    warnings: list[str] = Field(default_factory=list)
    truncated: bool = False
```

### 8.3 Scope 和权限

工具可见性由以下条件共同决定：

1. workflow kind；
2. subgoal tool scope；
3. authenticated caller permissions；
4. demo/cached/live mode；
5. tool risk level；
6. 当前预算和 provider capability。

隐藏工具时返回不可见的 toolset，不通过 prompt 告诉模型“你无权使用某工具”。权限校验还必须在工具函数服务端再次执行。

### 8.4 工具结果截断

保留当前每工具和总字符预算，但实现位置调整为 tool wrapper/capability：

- 单工具按 `max_result_chars` 截断；
- 总工具输出按 AgentBudget 限制；
- 截断结果必须带 `truncated=true` 和原长度；
- evidence quote、source URL 和 source ID 优先保留；
- 禁止把截断后的文本当作完整 filing/transcript；
- trace 记录截断原因和使用量。

## 9. Agent 设计

### 9.1 Research Agent

职责：选择只读工具、收集来源、产生证据候选和明确不确定性。

输出：

```python
class ResearchAgentOutput(BaseModel):
    summary: str
    evidence_candidates: list[EvidenceCandidate]
    claims: list[Claim]
    uncertainties: list[str]
    suggested_next_steps: list[str]
```

禁止：

- 返回只有 `final_answer: str` 而没有 evidence references；
- 把搜索摘要直接标记为 confirmed fact；
- 直接写 graph、snapshot 或 thesis。

### 9.2 Extraction Agent

职责：从已提供的 filing、transcript 或网页文本中提取 typed entities、relations、claims、risks 和 evidence。

候选输出复用：

- `ExtractionResult`；
- `ExtractedRisk`；
- `SupplierRelationExtraction`；
- `ManagementPeriodSnapshot` 相关模型。

迁移后删除对应 LLM 路径中的 fenced JSON 提取和宽松 `_coerce_*`；fixture 文件的 `json.loads` 继续保留。

### 9.3 Planner Agent

职责：返回一个 `AgentDecision`，不直接执行工具。

output validator 必须检查：

- scope 存在且授权；
- subgoal ID 唯一；
- `depends_on` 不引用未知 subgoal；
- 依赖关系无环；
- `stop` 包含 `stop_reason`；
- 非 `stop` 不包含 `stop_reason`；
- success criteria 可以通过可获得证据判断；
- 不允许选择 write-gated tool 作为未审批动作。

失败处理：先进行有限 output retry，仍失败时使用当前 `_deterministic_decision()`，并记录 fallback。

### 9.4 Supply Chain / Graph Reasoning Agent

Agent 只输出候选：

```python
class SupplyChainDiscoveryOutput(BaseModel):
    candidates: list[SupplierCandidate]
    proposed_edges: list[SupplyChainEdgeProposal]
    unresolved_entities: list[str]
    warnings: list[str]
```

确定性代码负责：

- 实体归一化；
- 自供应商和重复边剔除；
- relation type allowlist；
- evidence ID 存在性；
- confirmed/candidate/hypothesis 状态；
- graph projection 与 Sankey 构建。

### 9.5 Report Agent

输入只能是已经归一化、评分和经过基础 guardrail 的 typed data。输出为 `RiskReportV16` 或当前 canonical report model。

output validator 检查：

- 每个 top risk 有 evidence；
- evidence ID 和 graph path ID 存在；
- evidence 与 inference 分离；
- limitations 非空；
- 禁用直接买卖建议；
- 引用不超出提供的 source manifest。

最终 evaluator 仍在 Agent 外执行，并可以把状态降为 `needs_review` 或 `failed`。

## 10. Workflow 与 Pydantic Graph 设计

### 10.1 FinRisk 映射

| 当前步骤 | 目标实现 | 变更级别 |
| --- | --- | --- |
| Company Resolver | 确定性节点，保持 | 无/低 |
| Filing Risk Extraction | Extraction Agent | 高 |
| Market Evidence Collection | Research Agent | 高，首个垂直切片 |
| Evidence Normalization | 确定性节点，保持 | 低 |
| Risk Scoring | 确定性节点，保持 | 无 |
| Lifecycle Classifier | 规则优先，Agent 可补充 | 中 |
| Graph Reasoning | Agent 解释 + 确定性验证 | 中 |
| Structured Report | Report Agent | 高 |
| Evaluator | 确定性质量门禁，保持 | 无/低 |

### 10.2 Supply Chain 映射

```text
Product Resolver
→ Requirement Decomposition Agent
→ Supplier Discovery Agent(s)
→ Evidence Normalizer
→ Deterministic Edge Validator
→ Graph Projection
→ Sankey Builder
→ Evaluator
```

### 10.3 并行执行规则

只有顺序版通过合同验收后，才允许并行 filing、market、transcript 或 supplier discovery。

并行节点必须：

- 接收不可变输入快照；
- 返回 typed patch/result；
- 通过 reducer 合并；
- 不同时修改同一个 `FinRiskWorkflowState`/`SupplyChainExploreState`；
- 保证 reducer 幂等；
- 对结果排序，避免完成顺序造成 JSON snapshot 抖动；
- 单分支失败时按 critical/non-critical policy 明确处理。

## 11. 状态、消息、trace 与持久化

### 11.1 三类状态分离

| 状态 | 用途 | 持久化方式 |
| --- | --- | --- |
| `AgentRunState` | API/UI 业务状态 | 继续使用现有 store |
| Pydantic AI `ModelMessage` history | 模型上下文、tool/retry history | 新增版本化 JSON 字段/表 |
| OTel/project trace | 调试、指标、审计 | 现有 trace 投影 + 可选 OTel backend |

### 11.2 兼容投影

新增 `AgentRunRecorder`，将 Pydantic AI run events 投影为：

- `LLMCall`；
- `ToolExecutionEvent`；
- `ToolLoopTrace`；
- `AgentRunTrace`；
- timeline API 所需的 decision/subgoal/tool event；
- usage/cost/latency metrics。

必须保持现有 `/agent-runs`、`/timeline`、`/trace.json` 和 review endpoints 合同，除非另行进行 API versioning。

### 11.3 新增持久化字段

建议存储：

- `message_history_json`；
- `message_schema_version`；
- `pydantic_ai_run_id`；
- `conversation_id`；
- `agent_name`；
- `usage_json`；
- `model_name`；
- `provider_name`；
- `started_at`、`completed_at`；
- `parent_run_id`/`parent_subgoal_id`。

迁移必须支持旧记录缺少这些字段，并提供明确默认值；旧 trace 不做不可逆重写。

## 12. Retry、timeout 与预算

### 12.1 分层定义

| 层 | 处理对象 | 配置位置 |
| --- | --- | --- |
| Transport retry | 429、5xx、连接重置 | provider HTTP transport |
| Model fallback | provider/model 不可用 | model factory/fallback model |
| Tool retry | 参数校验、`ModelRetry`、tool timeout | Agent/tool config |
| Output retry | 最终结构和业务 output validator | Agent output config |
| Workflow retry | 整个节点/步骤 | application service/graph |

禁止把上述重试统一为一个 `max_tool_rounds`。

### 12.2 建议初始限制

初始值必须通过配置而不是散落常量表达：

```python
retries = {"tools": 2, "output": 2}

UsageLimits(
    request_limit=12,
    tool_calls_limit=20,
    total_tokens_limit=50_000,
)
```

继续保留项目级限制：

- `max_subgoals`；
- `max_total_runtime_seconds`；
- `max_total_fetch_pages`；
- `max_total_tool_result_chars`；
- `max_browser_steps`；
- 可选 `cost_limit`。

### 12.3 预算验收

必须证明：

- 到达 request/tool/token/runtime 任一上限后可预测地停止；
- 停止原因映射为现有 `AgentStopReason`；
- 已收集证据不丢失；
- 不把 budget exhaustion 记录为普通成功；
- retry 次数和真实模型请求数可以从 trace 还原；
- delegate Agent 使用共享 usage，不能绕过父运行预算。

## 13. Human-in-the-loop 与安全

现有 evidence candidate review 是业务复核，继续保留。

未来 write-gated 工具使用 deferred approval：

- graph write；
- thesis/watchlist/expectation 修改；
- 外部通知；
- 其他具有外部副作用的操作。

服务端安全规则：

1. approval 不是 authentication/authorization；
2. 工具执行时再次校验 caller、tenant、scope 和对象权限；
3. 服务端保存 pending call ID、validated args 和审批状态；
4. resume 时校验 call ID 未使用、未过期且属于当前用户；
5. 客户端提交的 message history 视为不可信输入；
6. secret、完整 provider response 和敏感 headers 必须经过 redaction；
7. browser/web 工具继续经过 SSRF 和 redirect 校验；
8. 审批拒绝、过期和参数覆盖都写入审计 trace。

## 14. 测试策略

### 14.1 测试层级

| 层级 | 目的 | 模型 |
| --- | --- | --- |
| Pure unit | 领域计算、validator、reducer | 不使用模型 |
| Agent unit | tool registration、output、retry | `TestModel` |
| Agent behavior | 精确 tool call/message path | `FunctionModel` |
| Contract | API、state、trace、store 兼容 | fake provider |
| Shadow | 新旧路径比较 | 同一输入、可选 live model |
| Eval | grounding、tool choice、报告质量 | golden dataset |
| Live acceptance | provider 真实兼容性 | DeepSeek/SGLang/vLLM |

### 14.2 CI 防真实调用

测试环境必须全局设置：

```python
from pydantic_ai import models

models.ALLOW_MODEL_REQUESTS = False
```

真实 provider 测试必须使用 `integration` marker，并由显式环境变量开启。

### 14.3 必须新增的合同测试

1. 13 个工具名称与 scope snapshot；
2. 参数约束和 Pydantic AI 生成 schema snapshot；
3. 工具返回 envelope；
4. invalid tool args 触发 retry；
5. invalid output 触发 output retry；
6. retry exhausted 映射为 fallback/review；
7. `AgentRunState` SQLite round-trip；
8. message history round-trip；
9. run ID/conversation ID correlation；
10. trace redaction；
11. usage/budget stop；
12. deferred approval approve/deny/expired/replay；
13. demo/cached 模式零网络请求；
14. provider capability 差异；
15. new/legacy output projection equality。

### 14.4 Eval 指标

至少跟踪：

- extraction precision/recall；
- claim grounding；
- evidence coverage；
- source diversity；
- invalid citation rate；
- hallucination risk；
- financial advice violation；
- confirmed edge evidence coverage；
- tool selection correctness；
- empty/no-tool completion rate；
- retry rate；
- tokens、requests、tool calls、latency 和可计算 cost。

## 15. 分阶段执行与验收

每一阶段单独提交或拆成多个小 PR。只有当前阶段满足退出条件后，下一阶段才可以把新能力设为默认。

### PAI-0：基线、ADR 与迁移开关

#### 目标

建立可重复基线和开关，不改变生产执行路径。

#### 执行步骤

1. 新增架构决策记录，确认混合架构和非目标。
2. 运行全量后端测试并记录 passed/skipped/failed。
3. 运行当前 Agent/Tool/API 定向测试。
4. 保存三类代表 fixture：FinRisk、Supply Chain、generic research。
5. 记录 13 个工具的 name/schema/scope/risk/evidence kind snapshot。
6. 记录现有 API response 和 trace snapshot。
7. 增加配置开关：
   - `legacy`；
   - `pydantic_ai_shadow`；
   - `pydantic_ai_primary`。
8. 默认保持 `legacy`。

#### 验证命令

```bash
uv sync --frozen
uv run pytest -m "not integration" -q --maxfail=1
uv run pytest -q \
  tests/agents \
  tests/tools/test_tool_catalog.py \
  tests/tools/test_tool_contracts.py \
  tests/workflows/test_finrisk_agent_workflow.py \
  tests/supply_chain/test_agent_workflow.py \
  tests/api/test_agent_runs_api.py
```

#### 验收门禁

- 全量非 integration 测试无失败；
- 定向 Agent 契约测试无失败；
- baseline artifact 可以被测试读取；
- 默认配置的行为、API 和 trace 与迁移前一致；
- `STATUS.md` 只在基线确实变化后更新。

#### 回滚点

删除新开关和基线辅助代码即可；无依赖、存储或主路径变化。

#### 交付物

- ADR；
- baseline snapshots；
- migration feature flag；
- 基线测试记录。

#### 实施记录

PAI-0 已于 2026-08-23 实施。架构决策见
[Pydantic AI 混合运行时 ADR](ADR_PYDANTIC_AI_RUNTIME.md)，测试结果和固化
契约见 [PAI-0 基线记录](validation/pydantic-ai-pai-0-baseline.md)。默认路径
仍为 `legacy`，尚未改变生产执行行为。

### PAI-1：依赖、Model factory 和最小 Agent

#### 目标

引入 Pydantic AI，但不接管现有 workflow。

#### 执行步骤

1. 在 `pyproject.toml` 增加显式 Pydantic 和 Pydantic AI 依赖。
2. 更新并提交 `uv.lock`。
3. 创建 `src/ai/model_factory.py`。
4. 为 DeepSeek、SGLang、vLLM 创建 typed provider config。
5. 创建 `AgentDeps`、`AgentPermissions` 和 `AgentSubject`。
6. 创建一个无业务副作用的 smoke Agent。
7. 添加 `TestModel`/`FunctionModel` 测试。
8. 在 test bootstrap 中禁止真实模型请求。
9. 增加 provider mock contract tests。

#### 验证命令

```bash
uv lock --check
uv sync --frozen
uv run pytest tests/ai/test_model_factory.py tests/ai/test_deps.py -q
uv run pytest -m "not integration" -q --maxfail=1
uv run ruff check src/ai tests/ai
```

#### 验收门禁

- 三种 provider 都能生成正确的 model/provider 配置；
- custom base URL 不会回退到公共 OpenAI endpoint；
- 测试中真实 model request 被阻止；
- smoke Agent 能产生 typed output；
- 没有修改现有 `/agent-runs` 和 workflow 默认行为；
- dependency lock 可在 CI 使用 `--frozen` 安装。

#### 回滚点

新模块尚未被生产路径引用；回滚依赖和 `src/ai` 即可。

#### 交付物

- dependency lock；
- model factory；
- deps contract；
- provider mock matrix。

#### 实施记录

PAI-1 已于 2026-08-23 实施并保持 legacy 默认路径。依赖版本、provider matrix、
占位凭据 fail-fast、smoke Agent 和全量回归结果见
[PAI-1 验收记录](validation/pydantic-ai-pai-1-validation.md)。

### PAI-2：Typed Toolsets 与兼容适配器

#### 目标

迁移现有 13 个工具的模型可见定义，同时保持底层服务和返回 envelope 不变。

#### 执行步骤

1. 按 company/market/supply-chain 建立 FunctionToolset。
2. 将手写 parameters schema 转换为 Python signature/Pydantic model。
3. 保留 metadata：scope、risk、evidence kind、result limit。
4. 实现动态 scope/permission 过滤。
5. 将同步和异步 callable 统一为 async wrapper。
6. 保留结果截断和稳定 envelope。
7. 创建 `PydanticAIRuntimeAdapter`，满足当前 `SubgoalRuntime` 调用侧。
8. 将 Pydantic AI tool event 投影为 `ToolExecutionEvent`。
9. 对每个工具运行 legacy/new contract parity test。

#### 验证命令

```bash
uv run pytest \
  tests/ai/test_toolsets.py \
  tests/ai/test_runtime_adapter.py \
  tests/tools/test_tool_catalog.py \
  tests/tools/test_tool_contracts.py \
  tests/tools/test_data_tool_catalog.py \
  tests/tools/test_graph_browser_tool_boundaries.py -q
uv run ruff check src/ai src/tools tests/ai tests/tools
```

#### 验收门禁

- 13 个工具全部具有 typed args 和稳定返回类型；
- legacy/new 的工具名、scope、risk level 和 evidence kind 一致；
- 非授权 scope 看不到对应工具；
- write-gated 工具不能进入 default scope；
- 截断、异常和 timeout 形成可审计 event；
- adapter 可以在不修改 `GlobalAgentRuntime` 的情况下执行一个 subgoal；
- 现有 tools tests 全部通过。

#### 回滚点

feature flag 切回 legacy tool catalog；旧 `ProjectTool` 不删除。

#### 交付物

- typed toolsets；
- runtime adapter；
- tool parity report；
- tool schema snapshots。

#### 实施记录

PAI-2 已于 2026-08-23 实施。13 个工具的 typed schema、动态权限、事件投影、
legacy adapter 和回归结果见
[PAI-2 验收记录](validation/pydantic-ai-pai-2-validation.md)。旧工具目录仍保留，
默认运行时未切换。

### PAI-3：Market Research 垂直切片

#### 目标

以 `MarketExplorerStep` 为第一条生产垂直链路，证明 Agent、工具、证据和 trace 能完整闭环。

#### 执行步骤

1. 实现 `ResearchAgentOutput`。
2. 创建 Market Research Agent 和 instructions。
3. 增加 evidence/source/uncertainty output validator。
4. 将新 Agent 接入 `MarketExplorerStep` 的 shadow 模式。
5. legacy 路径继续写正式 `market_evidence`；shadow 只写独立比较 artifact。
6. 比较 source URL、evidence kind、accepted/review 数量和 latency。
7. 对 no-tool、low-quality、timeout 和 malformed output 建立测试。
8. shadow 达标后增加 `pydantic_ai_primary`，但保留 legacy fallback。

#### 验证命令

```bash
uv run pytest \
  tests/ai/test_research_agent.py \
  tests/workflows/test_llm_market_explorer_step.py \
  tests/workflows/test_real_mode_fallbacks.py \
  tests/agents/test_global_agent_runtime.py \
  tests/api/test_agent_runs_api.py -q
uv run pytest -m "not integration" -q --maxfail=1
```

#### Shadow 验收指标

- 新路径所有 accepted evidence 都有 URL/source ID 和非空 quote/summary；
- invalid citation rate 为 0；
- 没有工具证据时状态为 `needs_review` 或明确 fallback；
- 新路径不会改变 legacy 最终报告；
- 新旧 source coverage 差异有解释和 artifact；
- trace 可还原模型请求、工具调用、retry、budget 和 fallback。

#### Primary 验收门禁

- fixture/demo 合同结果不退化；
- 代表 live/cached case 的 evidence coverage 不低于 legacy；
- guardrail failure 不高于 legacy baseline；
- p95 latency 和平均 requests/tool calls 在预设预算内；
- 连续两次验收运行结果满足确定的稳定性阈值；
- feature flag 可以即时切回 legacy。

#### 回滚点

将 Market Explorer 配置切回 legacy primary；保留 shadow artifact 供分析。

#### 交付物

- Market Research Agent；
- shadow comparison report；
- primary readiness record；
- fallback tests。

#### 实施记录

PAI-3 已于 2026-08-23 完成 fixture/cached primary 验收。typed output、shadow
artifact、fallback 和全量回归见
[PAI-3 验收记录](validation/pydantic-ai-pai-3-validation.md)。外部 live provider
验收保留为部署环境 integration gate。

### PAI-4：结构化 Extraction、Planner、Graph 与 Report

#### 目标

逐个替换手工 LLM JSON 解析点，统一 typed output、retry 和 fallback。

#### 建议迁移顺序

1. Supply Chain relation extraction；
2. Filing risk extraction；
3. Planner `AgentDecision`；
4. Graph insight interpretation；
5. Report generation。

每个子项必须独立 PR，不能在一个 PR 中同时替换五类输出。

#### 每个子项的执行模板

1. 定义或复用 canonical output model。
2. 明确哪些错误属于 Pydantic validation，哪些属于业务 validator。
3. 实现 output validator 和有限 `ModelRetry`。
4. 实现 deterministic fallback。
5. 先 shadow 对比。
6. 通过 domain-specific golden cases。
7. 切 primary。
8. 只删除该路径已经无引用的 JSON helper。

#### 验证命令

```bash
uv run pytest tests/agents/test_extraction_agent.py -q
uv run pytest tests/supply_chain/test_llm_json.py tests/supply_chain/test_llm_supplier_discovery.py -q
uv run pytest tests/agents/test_agent_planner_v21.py -q
uv run pytest tests/graph_reasoning tests/workflows/test_guardrails.py -q
uv run pytest tests/pipelines/test_generate_report.py tests/reports -q
uv run pytest -m "not integration" -q --maxfail=1
```

#### 验收门禁

- malformed output 不再静默变为空模型；
- retry exhausted 必须产生可定位 fallback/review finding；
- planner 无权选择未知 scope/tool；
- confirmed supply-chain edge 100% 有 accepted evidence；
- graph insight 的 path/evidence IDs 100% 可解析；
- report top risks 100% 有 evidence；
- financial advice guardrail 无退化；
- 被删除 helper 已无生产引用并有替代测试。

#### 回滚点

每个 Agent 独立 feature flag；失败只回滚该 output path，不影响已迁移工具基础层。

#### 交付物

- 五类 typed Agent/output；
- output retry tests；
- domain parity/eval reports；
- 已删除 helper 清单。

#### 实施记录

PAI-4 的五类 typed Agent/output contract 已于 2026-08-23 落地并通过 domain
测试；随后已将 typed planner、filing chunk extraction 和 supply-chain relation
extraction 接入 `pydantic_ai_primary` 生产边界，见
[PAI-4 验收记录](validation/pydantic-ai-pai-4-validation.md)。Graph/report 的现有
生产步骤是确定性计算，不为迁移而新增模型调用。Legacy JSON helper 仍承担
shadow/回滚职责，本阶段没有提前删除。

### PAI-5：Pydantic Graph 外层编排

#### 目标

将已经稳定的 Agent 节点和确定性节点纳入 typed graph，先保持顺序语义，再引入安全并行。

#### 执行步骤

1. 定义 graph state、deps、node input/output 和 terminal result。
2. 一比一表达现有 FinRisk 顺序流程。
3. 一比一表达现有 Supply Chain 顺序流程。
4. 映射 critical/non-critical failure policy。
5. 映射 `completed | needs_review | failed`。
6. 建立 graph result → 现有 workflow state 投影。
7. 运行顺序 parity tests。
8. 只在顺序版通过后，引入 filing/market/transcript 并行。
9. 使用 reducer 合并 typed results，并对输出稳定排序。
10. 增加取消、timeout、空分支、单分支失败测试。

#### 验证命令

```bash
uv run pytest \
  tests/ai/graphs/test_finrisk_graph.py \
  tests/ai/graphs/test_supply_chain_graph.py \
  tests/workflows/test_workflow_contract.py \
  tests/workflows/test_v16_quality_gated_orchestrator.py \
  tests/supply_chain/test_workflow_demo.py \
  tests/supply_chain/test_recursive_expansion.py -q
uv run pytest -m "not integration" -q --maxfail=1
```

#### 顺序版验收门禁

- step 顺序和 trace terminal status 与旧 workflow 一致；
- critical/non-critical 失败语义一致；
- 最终 workflow state JSON contract 一致；
- demo fixture 输出满足原有全部合同测试；
- graph 不直接绕过 quality gate。

#### 并行版验收门禁

- 不存在共享可变 state race；
- reducer 对相同输入重复执行结果一致；
- JSON 输出顺序稳定；
- 并行失败不会丢失成功分支证据；
- 与顺序版相比 wall time 有可测改进；
- provider rate limit 和总预算仍生效。

#### 回滚点

application service 继续可以调用旧顺序 workflow；graph 按 workflow kind 独立开关。

#### 交付物

- FinRisk graph；
- Supply Chain graph；
- reducer/idempotency tests；
- sequential/parallel benchmark。

#### 实施记录

PAI-5 顺序图与 reducer 已于 2026-08-23 通过 parity 验收，且并行准入策略已用
可执行 dependency gate 验证，见
[PAI-5 验收记录](validation/pydantic-ai-pai-5-validation.md)。由于当前业务节点
存在真实数据依赖，共享 mutable state 的生产并行被 gate 明确拒绝并保持关闭。

### PAI-6：消息持久化、恢复、审批与流式事件

#### 目标

把运行从“单进程内完成”升级为可暂停、可审计、可恢复的应用流程，但仍不引入外部 durable runtime。

#### 执行步骤

1. 版本化存储 Pydantic AI message history。
2. 存储 run ID、conversation ID、usage 和 agent name。
3. 实现 recorder 的幂等 append/update。
4. 将 `run_stream_events()` 投影为内部事件。
5. 可选增加 SSE/WebSocket endpoint。
6. 为 write-gated tool 引入 deferred approval。
7. 将 pending call、审批和结果保存在服务端。
8. 实现 resume、deny、expire、cancel 和 replay protection。
9. 执行进程中断/重启恢复测试。
10. 可选接入 OTel backend；默认必须允许禁用内容采集。

#### 验证命令

```bash
uv run pytest \
  tests/ai/test_message_store.py \
  tests/ai/test_recorder.py \
  tests/ai/test_deferred_tools.py \
  tests/ai/test_stream_events.py \
  tests/api/test_agent_runs_api.py \
  tests/api/test_agent_trace_redaction.py \
  tests/api/test_run_store.py -q
```

#### 验收门禁

- message history round-trip 后可继续同一 conversation；
- 每次 resume 使用新的 run ID，并保留 conversation correlation；
- 重启后不会重复执行已成功的写操作；
- approval deny/expire/replay 都被拒绝并记录；
- 未授权客户端无法仅凭 message history 执行写工具；
- trace、SSE 和下载结果完成 redaction；
- 旧数据库记录仍可读取；
- migration 和 rollback 均经过副本演练。

#### 回滚点

新存储字段只追加，不破坏旧 schema；关闭 resume/stream/approval 开关后旧读取路径继续工作。

#### 交付物

- message persistence；
- deferred approval；
- recovery tests；
- optional streaming/OTel integration。

#### 实施记录

PAI-6 的核心 message persistence、recorder、服务端 API resume、stream event
projection 与 SQLite 原子 deferred approval 已于 2026-08-23 验收，见
[PAI-6 验收记录](validation/pydantic-ai-pai-6-validation.md)。SSE/WebSocket 与
OTel 保持可选，未成为运行依赖。

### PAI-7：默认切换与旧代码退役

#### 目标

将 Pydantic AI 设为默认主路径，并删除不再需要的自研模型循环。

#### 删除候选

- `OpenAICompatibleToolLoop`；
- `JSONToolChoiceToolLoop`；
- `LLMToolAgentRuntime`；
- 旧 `AgentRuntime`；
- 无引用的手写 OpenAI tool schema；
- 无引用的 LLM fenced JSON/coerce helper；
- 仅为旧 trace 生成存在的 adapter。

删除前必须通过 `rg`、import test 和完整测试确认没有生产引用。

#### 执行步骤

1. Pydantic AI primary 连续通过 shadow/live acceptance。
2. 将默认 feature flag 切换为 Pydantic AI。
3. 保留至少一个发布周期的 legacy emergency flag。
4. 统计 emergency fallback 实际使用量。
5. 使用 `rg` 建立旧代码引用清单。
6. 分模块删除旧实现和测试替身。
7. 更新 `ARCHITECTURE.md`、`STATUS.md`、README 和运维文档。
8. 删除 emergency flag。
9. 执行完整发布门禁。

#### 验证命令

```bash
uv run pytest -m "not integration" -q --maxfail=1
uv run ruff check src/ai src/agents src/llm src/tools src/workflows src/supply_chain
uv run python -m pytest tests/test_import_all_modules.py -q
uv run python -m src.workflows.finrisk_workflow \
  --ticker AAPL \
  --analysis-goal "Identify evidence-backed risks." \
  --demo-mode
uv run python scripts/pydantic_ai_live_acceptance.py \
  --provider <sglang|vllm|deepseek> \
  --output artifacts/pydantic-ai/provider-live.json
uv run python scripts/pydantic_ai_observation_gate.py \
  --required-runs 20 --required-hours 168 \
  --output artifacts/pydantic-ai/primary-observation.json
```

根据当时的前端目录配置，再执行前端测试和 production build。

#### 验收门禁

- 全量非 integration 测试通过；
- 关键 live provider 验收通过或有明确、批准的跳过理由；
- golden/eval 不低于迁移前基线；
- API、trace、review、demo 和 cached 合同通过；
- 无生产模块导入已删除 runtime；
- 无 undocumented fallback；
- 文档和运维 runbook 已更新；
- `STATUS.md` 只记录实际完成并有证据的阶段。

#### 回滚点

删除 emergency flag 前必须保留一个可部署的迁移前 tag/commit。删除后回滚使用版本部署，不再在主干保留双实现。

#### 交付物

- 默认 Pydantic AI runtime；
- legacy removal report；
- 最终架构文档；
- release acceptance record。

#### 当前实施状态

Primary 接线和离线发布门禁已经完成，但默认切换与 legacy 删除尚未获准，原因、
引用盘点和精确后续门禁见
[PAI-7 切换准备记录](validation/pydantic-ai-pai-7-readiness.md)；可执行命令和
回滚步骤见 [切流 Runbook](guides/pydantic-ai-cutover.md)。在 live provider 验收与
发布观察期完成前，默认值有意保持 `legacy`。

## 16. 旧代码删除准入条件

一个旧组件只有同时满足以下条件才能删除：

1. 已有新组件承担全部生产职责；
2. 所有调用点已迁移；
3. 新旧 parity/shadow 验收通过；
4. 新路径至少有 unit、contract 和 failure-path tests；
5. feature flag 已在 primary 使用；
6. live/demo/cached 三种模式均有明确结果；
7. trace 和 API compatibility 已验证；
8. `rg` 无生产引用；
9. import-all test 通过；
10. 有版本级回滚点。

## 17. PR 拆分建议

建议至少拆成以下 PR，避免一次变更过大：

1. `docs/ADR + baseline + feature flags`
2. `dependencies + model factory + deps`
3. `company research toolset`
4. `market research toolset + adapter`
5. `supply chain toolset`
6. `market research shadow agent`
7. `market research primary readiness`
8. `supply-chain extraction agent`
9. `filing extraction agent`
10. `planner agent`
11. `graph reasoning agent`
12. `report agent`
13. `FinRisk graph sequential`
14. `Supply Chain graph sequential`
15. `safe parallel reducers`
16. `message persistence + recorder`
17. `deferred approval + recovery`
18. `default switch`
19. `legacy removal + final docs`

每个 PR 描述必须包含：

- 影响路径；
- 默认行为是否变化；
- 新增/变更的 schema；
- 测试命令和结果；
- shadow/parity artifact；
- 回滚方法；
- 已知限制。

## 18. 风险登记

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| Pydantic AI v2 API 仍快速演进 | 升级破坏 | 锁定 `<3`，大版本单独迁移 |
| SGLang/vLLM tool/schema 支持差异 | live 路径失败 | model profile、provider matrix、JSON fallback 仅作为受控兼容层 |
| 新旧 trace 格式不一致 | 前端/审计回归 | recorder 投影和 snapshot contract |
| Output retry 增加成本和延迟 | 预算超限 | tool/output retry 分开，usage limits，指标门禁 |
| 并行共享 state | 数据竞争和不稳定输出 | typed result + reducer，禁止共享可变 state |
| Agent 确认无证据事实 | 金融质量风险 | candidate-only、evidence validator、外部 guardrail |
| client history/approval 被伪造 | 未授权写入 | 服务端 pending state 和执行时授权 |
| 双实现长期共存 | 维护成本 | 阶段退出条件和 legacy 删除准入 |
| 测试误触真实模型 | 成本和不稳定 | `ALLOW_MODEL_REQUESTS=False` + integration marker |
| 存储 migration 不可逆 | 历史 run 损坏 | additive schema、备份、双读、恢复演练 |

## 19. 总体验收定义

迁移完成必须同时满足：

### 功能

- FinRisk、Supply Chain 和 generic research 主路径使用 Pydantic AI；
- 结构化输出、工具调用、retry、usage 和 message history 由 Pydantic AI 管理；
- 确定性评分、evaluator、guardrail 和写入边界未被弱化；
- API、timeline、trace、review 和 demo 路径保持可用。

### 质量

- accepted evidence 100% 可定位来源；
- confirmed graph edge 100% 有 accepted evidence；
- report top risk 100% 有 evidence reference；
- invalid citation rate 为 0；
- financial advice guardrail 不退化；
- golden/eval 指标不低于迁移前批准基线。

### 可靠性

- request、tool、token、runtime 和字符预算可预测停止；
- provider、tool、output 和 workflow failure 有不同 trace；
- demo/cached 模式无意外网络调用；
- 进程恢复不重复执行写操作；
- legacy fallback 使用量归零后才删除旧路径。

### 工程

- 全量非 integration 测试通过；
- 变更目录 Ruff 通过；
- lockfile 可 frozen install；
- import-all test 通过；
- 文档、运维和回滚说明完整；
- 无未记录的生产旧 runtime 引用。

## 20. 官方参考

- [Pydantic AI Agents](https://pydantic.dev/docs/ai/core-concepts/agent/)
- [Dependencies](https://pydantic.dev/docs/ai/core-concepts/dependencies/)
- [Structured Output](https://pydantic.dev/docs/ai/core-concepts/output/)
- [Function Tools](https://pydantic.dev/docs/ai/tools-toolsets/tools/)
- [Toolsets](https://pydantic.dev/docs/ai/tools-toolsets/toolsets/)
- [Retries](https://pydantic.dev/docs/ai/core-concepts/retries/)
- [Usage Limits](https://pydantic.dev/docs/ai/api/pydantic-ai/usage/)
- [Messages and Chat History](https://pydantic.dev/docs/ai/core-concepts/message-history/)
- [Multi-agent Applications](https://pydantic.dev/docs/ai/guides/multi-agent-applications/)
- [Pydantic Graph Builder](https://pydantic.dev/docs/ai/graph/builder/)
- [Deferred Tools and Approval](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/)
- [Unit Testing](https://pydantic.dev/docs/ai/guides/testing/)
- [OpenAI-compatible Models](https://pydantic.dev/docs/ai/models/openai/)
- [OpenTelemetry and Logfire](https://pydantic.dev/docs/ai/integrations/logfire/)
