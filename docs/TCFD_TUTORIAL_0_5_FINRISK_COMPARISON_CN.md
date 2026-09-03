# TCFD Tutorial 0–5 与 FinRisk 实现对照

## 1. 对照范围与阅读方法

本文对照两个仓库在 2026-09-03 的代码状态：

- TCFD / `frequency_analyzer`：分支 `tutorial/pydantic-ai`，提交
  `4ef1c0f49853d2821dbf1ead73259d65475ca8d3`；
- FinRisk / `fintext_llm`：分支 `tutorial/pydantic-ai-harness`，基线提交
  `a6115a75f56655492603bc63dabe0ce46dcbd7b0`。

TCFD Tutorial 0–5 是一个较小、边界清楚的教学项目。它围绕 TCFD 关键词抽取，逐步引入
模型工厂、typed Agent、typed dependencies、语义校验、程序化工作流和 eval。

FinRisk 不是同一业务的重写。它是一个更大的金融风险研究系统，包含 SEC filing、Web、
transcript、XBRL、图推理、供应链、报告、质量门禁和人工复核。因此本文比较的是“同一种
架构能力在 FinRisk 中如何实现”，不是强行把业务类名一一对应。

结论先行：

| TCFD 章节 | 教学目标 | FinRisk 覆盖程度 | 主要差异 |
| --- | --- | --- | --- |
| 0 | 唯一模型边界与 capability probe | 已覆盖并扩展 | FinRisk 支持四类 provider 和 per-run 配置，但 probe 较窄，`timeout_s` 尚未传入模型客户端 |
| 1 | typed output 与领域模型 | 已覆盖并扩展 | 从单一关键词 schema 扩展为 filing、研究、供应链、planner 等多类 typed output |
| 2 | typed deps 与 dynamic instructions | 部分覆盖 | typed deps、权限和服务注入更完整；业务上下文主要进入 prompt，未采用 dynamic instructions |
| 3 | 校验、重试、并发和显式失败 | 部分覆盖 | 校验、预算、状态和 guardrail 较完整；分块调用仍为顺序执行，失败合同也没有全路径统一 |
| 4 | 多 Agent 的程序化工作流 | 已覆盖并扩展 | 用三类 Pydantic Graph 和确定性步骤编排；TCFD 的 lexicon/cluster 任务在 FinRisk 中没有直接对应物 |
| 5 | 离线测试、eval、架构门禁 | 部分覆盖 | 有 30 个 workflow cases、Agent golden cases 和 source gate；缺少 TCFD 那种任务级 live eval 与完整 PR/F1 指标 |

## 2. Chapter 0：建立唯一模型边界

### 2.1 TCFD 定义了什么

教程文件：`frequency_analyzer/tutorials/00-local-model.md`。

本章定义四件事：

1. 用一个配置对象描述模型 endpoint、模型名、密钥、温度、超时和重试；
2. 所有运行时代码只通过一个模型工厂构造 Pydantic AI `Model`；
3. 用显式 live probe 分别验证普通文本、native structured output、prompted structured
   output 和 tool calling；
4. 默认测试禁止真实模型请求，live 验收必须显式运行。

TCFD 的实际实现如下：

| 文件 | 定义 | 功能 |
| --- | --- | --- |
| `src/tcfd_extractor/config.py` | `LLMSettings` | 从环境读取并校验唯一的 LLM 配置 |
| `src/tcfd_extractor/ai/model.py` | `build_model(settings)` | 创建 `httpx.AsyncClient`、`OpenAIProvider` 和 `OpenAIChatModel`；把 timeout、transport retry 和 temperature 固定在工厂边界 |
| `scripts/pydantic_ai_probe.py` | `probe_plain_text`、`probe_typed_output`、`probe_prompted_output`、`probe_tool_calling` | 对四项 provider 能力分别输出 PASS/FAIL、耗时和脱敏错误类型 |
| `tests/conftest.py` | `models.ALLOW_MODEL_REQUESTS = False` | 阻止默认测试误访问真实 endpoint |
| `tests/ai/test_model.py` 等 | 离线工厂和 probe 测试 | 验证配置覆盖、构造参数和失败返回码 |

TCFD 调用链是：

```text
LLMSettings
  -> build_model
  -> OpenAIProvider + OpenAIChatModel
  -> Agent(model=...)
```

### 2.2 FinRisk 如何实现同类能力

FinRisk 把这个边界扩展成“进程默认配置 + 每次运行覆盖 + provider 判别联合类型”。

| 文件 | 定义 | 功能 |
| --- | --- | --- |
| `src/schemas/llm_config.py` | `LLMProvider`、`LLMRunConfig` | 请求级选择 `sglang`、`vllm`、`deepseek` 或 `openai`，可覆盖 base URL 和 model |
| `src/ai/model_factory.py` | `SGLangModelConfig`、`VLLMModelConfig`、`DeepSeekModelConfig`、`OpenAIModelConfig` | 用 discriminated union 表达已解析、不可变、禁止额外字段的 provider 配置 |
| `src/ai/model_factory.py` | `resolve_agent_model_config` | 把 per-run 配置和 `Settings` 合并；配置错误明确失败，不静默换 provider |
| `src/ai/model_factory.py` | `_compatible_profile` | 为非 OpenAI endpoint 声明保守能力，例如禁用 native JSON Schema 和 strict tool definition |
| `src/ai/model_factory.py` | `build_agent_model` | 唯一创建 `OpenAIProvider` 和 `OpenAIChatModel` 的生产工厂 |
| `src/ai/live_acceptance.py` | `LiveAcceptanceOutput`、`LiveAcceptanceReport`、`run_live_acceptance` | 用一次合成请求同时验证 typed output、本地 typed tool call 和 usage |
| `scripts/pydantic_ai_live_acceptance.py` | `main` | 解析 provider 参数、调用模型工厂、运行验收、脱敏错误并输出 JSON |
| `docs/ADR_PYDANTIC_AI_RUNTIME.md` | 架构决策 | 明确 Pydantic AI 是唯一 Agent runtime，旧 runtime 不作为在线 fallback |
| `tests/conftest.py` | `models.ALLOW_MODEL_REQUESTS = False` | 与 TCFD 相同，默认测试禁用真实模型请求 |

FinRisk 的生产调用链是：

```text
FinRiskRequest.llm_config / CLI provider 参数
  -> resolve_agent_model_config(run_config, Settings)
  -> AgentModelConfig
  -> build_agent_model
  -> OpenAIProvider + OpenAIChatModel
  -> typed Agent
```

相较 TCFD，FinRisk 的增强点是：

- 同一工厂支持本地 SGLang、vLLM 以及 DeepSeek、OpenAI；
- provider 是显式类型，不用字符串分支散落在 workflow；
- 请求可以选择 provider，而不修改全局环境变量；
- 非 OpenAI 服务使用保守 capability profile，避免假设服务支持 native schema；
- live 输出包含 request/token usage，CLI 会脱敏异常内容；
- ADR 明确区分“模型 runtime 回退”和“业务数据降级”。FinRisk 允许 cached、fixture 或
  确定性业务降级，但不恢复第二套 LLM runtime。

### 2.3 尚未与 TCFD 完全对齐的地方

1. TCFD probe 独立测试 plain text、native output、prompted output 和 tool calling；FinRisk
   只用一次请求联合验证 typed output、一个本地工具和 usage。它不能分别定位 native 与
   prompted structured output 的兼容性。
2. FinRisk 的 `_OpenAICompatibleConfig` 定义了 `timeout_s`，但当前
   `build_agent_model` 没有把它传给 HTTP client、provider 或 model settings。TCFD 的
   `build_model` 则真正应用了 timeout、transport retry 和 temperature。

因此 Chapter 0 的“唯一模型边界”已经完成，provider 治理比 TCFD 更丰富；但 capability
矩阵和 timeout 落地仍可加强。

## 3. Chapter 1：用 typed Agent 重建模型输出边界

### 3.1 TCFD 定义了什么

教程文件：`frequency_analyzer/tutorials/01-typed-agent.md`。

本章不再让模型返回自由字典，而是先定义领域输出，再定义 Agent 和调用方。

| 文件 | 定义 | 功能 |
| --- | --- | --- |
| `src/tcfd_extractor/domain/keywords.py` | `TCFDKeywords` | 四个固定维度：`policy`、`market`、`technology`、`reputation`；拒绝额外字段 |
| 同上 | `merge_keywords(items)` | 纯函数、按首次出现顺序合并并去重四个维度 |
| `src/tcfd_extractor/ai/agents/keyword.py` | `create_keyword_agent(model)` | 建立 `Agent[KeywordRunDeps, TCFDKeywords]`，模型输出直接成为 Pydantic 对象 |
| `src/tcfd_extractor/workflows/extraction.py` | `extract_chunk` | 调用 `agent.run`，把 `result.output` 与 `source_id/chunk_index` 组合为 `ChunkExtraction` |
| `src/tcfd_extractor/io/*` | text、lexicon、exporter 边界 | 文件格式和中文导出标签留在 I/O 层，不污染领域 schema |

TCFD 的关键思想是：Pydantic schema 是模型输出的真相源，workflow 消费对象，不再手工
解析 JSON 或检查任意 dict key。

### 3.2 FinRisk 的领域输出

FinRisk 把相同原则应用到了多个业务边界。

主风险工作流的公共 schema 位于 `src/schemas/finrisk.py`：

| 类型 | 表达的业务事实 |
| --- | --- |
| `FinRiskRequest` | ticker、研究目标、时间范围、数据源、浏览预算和 per-run LLM 配置 |
| `CompanyProfile` | 已解析的公司、CIK、filing 类型、年份和来源 |
| `ExtractedRisk` | 风险类型、严重度、原文 quote、来源、section 和 confidence |
| `MarketEvidence` | Web/搜索证据、URL、claim、支持/反驳关系和时间 |
| `NormalizedEvidence` | filing、Web、transcript 的统一证据结构 |
| `RiskScore` | 可解释的确定性风险评分分解 |
| `GraphInsight` | 有支持证据的二阶图路径 |
| `RiskReport` | 风险、评分、证据、图洞察、限制和 Markdown 报告 |
| `FinRiskWorkflowState` | 九步 workflow 之间传递的唯一公共状态对象 |

真正作为 Pydantic AI 输出的专用 schema 位于 `src/ai/agents/structured.py` 和
`src/ai/agents/research.py`：

| Agent 输出 | Builder | 功能 |
| --- | --- | --- |
| `FilingRiskExtractionOutput` | `build_filing_extraction_agent` | 从 filing 文本提取 `ExtractedRisk`，同时返回 warnings 和 `needs_review` |
| `SupplierRelationBatch` | `build_relation_extraction_agent` | 提取有来源的供应商关系 |
| `RequirementDecomposition` | `build_requirement_decomposition_agent` | 把产品拆成上游 component/service/infrastructure 等需求 |
| `SupplierProposalBatch` | `build_supplier_proposal_agent` | 产生明确标记为 hypothesis 的供应商候选 |
| `NodeProfileBatch` | `build_node_profile_agent` | 生成供应链节点卡片 |
| `ExtractionResult` | `build_generic_extraction_agent` | 通用 entity/relation/claim/evidence 抽取 |
| `AgentDecision` | `build_planner_agent` | planner 的工具、scope、subgoal 或 stop 决策 |
| `ResearchAgentOutput` | `build_market_research_agent` | 带 source ID、URL、证据、uncertainty 和 next checks 的研究结论 |

### 3.3 最接近 TCFD keyword extraction 的 FinRisk 调用链

最直接的对应物是 filing risk extraction：

```text
FilingRiskExtractorStep
  -> 获取 10-K / 10-Q
  -> SectionParser 选择实质性 Item 1A
  -> PydanticAIFilingExtractionClient.extract_risks_chunked
  -> chunk_text 生成带 source/section/offset 的 TextChunk
  -> build_filing_extraction_agent
  -> Agent.run(prompt, deps)
  -> FilingRiskExtractionOutput
  -> ExtractedRisk + ChunkValidation + LLMCall
  -> FinRiskWorkflowState.filing_risks / chunk_validations / llm_log
```

对应脚本和定义：

- `src/agents/extraction_agent.py::TextChunk` 保存 source、section 和字符偏移；
- `src/agents/extraction_agent.py::chunk_text` 生成重叠字符窗口；
- `src/ai/structured_clients.py::PydanticAIFilingExtractionClient` 把 typed Agent 适配到
  已有的 filing step 协议；
- `extract_risks_chunked` 为每个 chunk 建 deps、执行 Agent、收集 typed risks，并记录
  `ChunkValidation`、完整消息、structured response、tokens 和 latency；
- `src/workflows/steps/filing_risk_extractor.py::FilingRiskExtractorStep` 负责 SEC 获取、
  section 选择、调用 typed client、降级和状态写入。

### 3.4 与 TCFD 的差异

- FinRisk 没有 `TCFDKeywords` 的四维关键词业务，也没有 `merge_keywords` 的直接等价物。
- TCFD 的输出很小且独立；FinRisk 为保持 API、持久化和前端合同，保留了较大的
  `FinRiskWorkflowState`，但每个模型边界仍使用较小的专用 output model。
- FinRisk 额外记录每个 chunk 的位置、校验结果、消息、token 和 latency，满足产品级审计。
- TCFD 在这一章就删除旧 extractor；FinRisk 的生产 builder 已指向 typed client，但
  `FilingRiskExtractorStep._chunked_llm_extract` 和 `_llm_extract` 中仍保留少量旧测试/第三方
  adapter 兼容分支。它们不是第二套模型 runtime，但说明“接口清理”没有 TCFD 那么彻底。

## 4. Chapter 2：把运行上下文建模为 dependencies

### 4.1 TCFD 定义了什么

教程文件：`frequency_analyzer/tutorials/02-dependencies.md`。

TCFD 把不同性质的数据分开：

- 用户文本仍作为 `agent.run` 的 prompt；
- 不应该被拼成松散字符串的运行时对象放进 typed deps；
- 依赖当前运行而变化的 system instructions 从 `RunContext` 动态生成。

核心定义位于 `src/tcfd_extractor/ai/deps.py`：

| deps | 字段 | 用途 |
| --- | --- | --- |
| `KeywordRunDeps` | lexicon、每维上限、source text | 动态 instructions 和 output validator |
| `RelevanceDeps` | `CooccurrenceContext` | 共现相关性判断 |
| `SummaryDeps` | `SummaryStats`、sample records | 只让模型写叙述，不重算数字 |
| `LexiconReviewDeps` | candidates | 词袋候选审核 |
| `ClusterLabelDeps` | cluster | cluster 命名 |

`src/tcfd_extractor/ai/agents/keyword.py::keyword_instructions` 从
`RunContext[KeywordRunDeps]` 读取 lexicon 和数量限制，构造本次运行的 instructions。词袋是
参考，不是脱离原文输出的白名单。

`SourceChunk`、`ChunkExtraction` 保证 `source_id` 和 `chunk_index` 从输入贯穿输出。

### 4.2 FinRisk 的 typed deps

FinRisk 的共享依赖定义在 `src/ai/deps.py`：

| 类型 | 定义的能力 |
| --- | --- |
| `AgentSubject` | 本次研究的 ticker、company、product 和 metadata |
| `AgentPermissions` | tool scopes、interactive 权限、write 权限；`allows` 是统一判定函数 |
| `AgentServices` | 注入 search router、tool catalog、evidence sink、trace sink、message recorder 和本次 tool events |
| `AgentDeps` | run ID、conversation ID、settings、subject、permissions、budget 和 services |
| `BrowserToolDeps` | 浏览器专用依赖：通用 `AgentDeps` 加受控 browser session |

它解决的生产问题比 TCFD 更多：

1. Agent 不从全局单例隐式取得工具、store 或 trace sink；
2. 每次运行可拥有不同 tool scope 和写入权限；
3. run/conversation ID 能关联消息、usage、trace 和恢复；
4. `AgentBudget` 对 subgoal、tool round、tool call、fetch page、总时长和结果字符数设限；
5. 同一 deps 可服务 planner、research、filing、supply chain 和 generic research。

典型 planner 调用链：

```text
AgentRunState
  -> PydanticAIPlanner.__call__
  -> 构造 AgentSubject(pending_subgoal_id, workflow_kind)
  -> 构造 AgentPermissions(available scopes)
  -> AgentDeps
  -> build_planner_agent
  -> output validator 从 ctx.deps 校验 subgoal、scope 和可见工具
  -> AgentDecision
```

工具可见性调用链：

```text
ToolCatalog
  -> build_project_function_toolset（typed Python 参数生成 tool schema）
  -> build_scoped_toolset
  -> is_visible(ctx.deps.permissions)
  -> _invoke_project_tool 再做执行时权限复核
  -> ToolResultEnvelope + ToolExecutionEvent
```

这里有两层权限检查：工具 schema 暴露前过滤一次，真正执行时再检查一次，避免调用方绕过
可见性层直接执行工具。

### 4.3 与 TCFD dynamic instructions 的差异

FinRisk 已实现 typed deps，但当前 `src/ai` 没有像 TCFD
`keyword_instructions(ctx)` 那样注册依赖 `RunContext` 的 dynamic instructions：

- planner 的 goal、pending subgoal、accepted evidence 和 available tools 被序列化进 prompt；
- filing 的 company/year/source/chunk 被写入 prompt，同时部分 metadata 放在
  `AgentSubject`；
- supply-chain 的业务上下文主要由 step 生成 prompt；
- deps 主要控制权限、服务、预算、消息记录和 output validation；
- 最接近“动态行为”的部分是 scoped toolset 和 planner output validator，而不是 system
  instructions。

所以 Chapter 2 的“把运行对象从全局状态中拿出来”已完成，而且更偏生产治理；但“用
dynamic instructions 根据 deps 构造本次 system prompt”并未直接实现。若面试时被追问，
不能说 FinRisk 完整复制了 TCFD 的 dynamic instructions 模式。

## 5. Chapter 3：结构校验、语义校验、重试、并发和显式失败

### 5.1 TCFD 定义了什么

教程文件：`frequency_analyzer/tutorials/03-validation.md`。

TCFD 明确区分三层校验：

1. Pydantic schema 校验字段、类型和范围；
2. Agent output validator 校验本次运行的业务语义；
3. workflow 负责批量执行、并发、错误分类和部分成功。

实际实现：

| 文件 | 定义 | 功能 |
| --- | --- | --- |
| `src/tcfd_extractor/ai/validation.py` | `normalize_keyword` | 只为比较做 NFKC、hyphen、casefold 和空白规范化，不改模型原始输出 |
| 同上 | `collect_keyword_violations` | 检查数量、空白、重复、长度、标点、句子和是否能在 source text 中找到 |
| `src/tcfd_extractor/ai/agents/keyword.py` | `validate_keyword_output` | output validator 调纯函数；有错误就抛 `ModelRetry`，最多反馈有限数量的错误 |
| `src/tcfd_extractor/domain/failures.py` | `FailureCategory` | 区分 invalid input、model transport、model output 和 unexpected |
| 同上 | `ChunkFailure`、`ReportExtraction` | 显式保存 successes 和 failures，空成功不等于调用失败 |
| `src/tcfd_extractor/workflows/extraction.py` | `extract_report` | 用 `asyncio.Semaphore` 控制并发，逐类映射异常，最终按 chunk index 稳定排序 |

TCFD 的原则是：结构合法不代表业务合法；语义错误应把反馈交回模型重试；重试耗尽或
transport 失败必须成为 typed failure，不能伪装成空关键词结果。

### 5.2 FinRisk 的结构与语义校验

FinRisk 使用四层机制：

#### 第一层：Pydantic 字段约束

`src/schemas/finrisk.py` 对 URL、非空文本、severity、confidence、risk path、source 和
workflow status 等做基础约束。供应链 schema 还限制列表长度、ticker 正规化、relation
方向和图结构。

#### 第二层：模型输出内部不变量

`src/ai/agents/structured.py` 和 `src/ai/agents/research.py` 定义关键业务校验：

- `SupplierRelationBatch.validate_confirmed_relations`：非 hypothesized 且 confidence
  不低于 0.55 的关系，必须有 HTTP(S) URL 和非空 quote；
- `FilingRiskExtractionOutput.validate_empty_result`：没有 risk 时必须明确
  `needs_review=True`，防止“空结果”静默成功；
- `ResearchAgentOutput.validate_grounding`：无 evidence 不能标 completed；无 evidence
  必须解释 uncertainty；source ID 不得重复；
- `AgentDecision._stop_requires_reason`：stop 决策必须给 stop reason，其他决策不能携带；
- `SupplyChainExploreRequest`、`SupplyChainEdge`、`SankeyPayload` 等 model validator
  约束请求和图的一致性。

这些校验发生在 typed output 构造时。结构或 model validator 失败由 Pydantic AI 的
structured-output 机制处理；FinRisk 没有为每个 specialist 单独声明统一的重试次数。

#### 第三层：显式 `ModelRetry`

FinRisk 当前明确抛出 `ModelRetry` 的主要位置是
`src/ai/agents/structured.py::validate_planner_scope`。它检查：

- 有 pending subgoal 时，decision 必须选择该 subgoal；
- selected scope 必须在本次 permissions 中；
- selected tool 必须存在于本次可见 catalog。

失败时把可修正的信息返回模型重试。与 TCFD 不同，filing、research 和 supplier relation
的语义约束主要写成 Pydantic model validator，而不是单独的 Agent output validator。

#### 第四层：workflow guardrails

`src/evaluation/validators/` 定义 schema、evidence、claim grounding、source quality、
financial safety、report structure 和 workflow validators。

`src/evaluation/engine.py::GuardrailEngine` 执行 validators，将 validator 自身异常转成
BLOCKER finding，而不是让审计链消失。

`src/workflows/quality_gate.py::run_step_with_quality_gate` 在步骤前后执行 guardrail；步骤
异常会把 state 标记为 failed。API 主路径通过
`src/workflows/v16_runner.py::run_finrisk_workflow_v16` 启用默认的七类 validator，并汇总
workflow evaluation。

这些 guardrail 是事后接受、降级或阻断机制，不会像 `ModelRetry` 那样要求模型重新生成。

### 5.3 FinRisk 的预算、并发和失败语义

预算实现：

- `src/agents/state.py::AgentBudget` 定义 subgoal、round、tool call、page、wall-clock 和
  tool-result-size 上限；
- `src/ai/usage.py::build_usage_limits` 把项目预算转换成 Pydantic AI `UsageLimits`；
- `src/ai/runtime_adapter.py::PydanticAIRuntimeAdapter` 对每个 subgoal 应用 request/tool
  limits；
- `src/ai/browser_client.py::explore` 用 `max_steps` 限制 request 和 tool call。

失败和降级实现：

- `ToolResultEnvelope` 明确区分 `success` 与 `failed`，并记录 error、warnings、truncated；
- `ToolExecutionEvent` 保存工具参数、状态、latency 和 error；
- `AgentRunState`、`AgentSubgoal` 有 `failed`、`needs_review`、`fallback` 和 stop reason；
- `GlobalAgentGraph` 捕获 subgoal runtime 异常，写 trace/fallback，并停止为
  `tool_failures`；
- `FilingRiskExtractorStep` 在 SEC、provider 或 extraction 失败时可转向 keyword/cached
  路径，并通过 `FallbackEvent` 或 `ChunkValidation.fallback_used` 暴露降级；
- `EvaluatorStep` 把最终结果映射为 completed、needs_review 或 failed。

### 5.4 没有与 TCFD 完全等价的部分

#### 分块执行不是有界异步并发

`PydanticAIFilingExtractionClient.extract_risks_chunked` 当前使用普通 `for` 循环逐 chunk
执行。FinRisk 的 FinRisk Graph 和 Supply Chain Graph 也是显式顺序图。

`src/ai/graphs/parallel_policy.py` 定义了未来并行前的读写冲突检查；当前 filing extractor
写 `filing_risks/llm_log`，market explorer 又读取 `filing_risks` 并写 `llm_log`，所以测试
明确禁止把两者直接并行。`reducers.py::merge_unique_sorted` 只提供未来安全 fan-out 的稳定
合并函数。

因此 FinRisk 有“并行安全策略”，但没有实现 TCFD Chapter 3 的
`Semaphore + asyncio.gather` 式 chunk-level bounded concurrency。

#### 失败合同尚未全路径统一

- `FilingRiskExtractionOutput` 防止空风险静默成功，这是正确的；
- 但 `src/agents/extraction_agent.py::_call_llm` 捕获异常后返回空 `ExtractionResult` 加 warning；
- `PydanticAIBrowserClient.summarize` 失败时返回页面前 200 字符，`explore` 失败时返回
  `None`；
- filing step 的兼容 helper 仍会捕获异常并切到 keyword fallback；
- `_build_llm_client` 在构造失败时返回 `None`，具体配置错误主要留在日志，未形成统一的
  per-chunk typed failure 对象。

这些路径大多保留 warning、trace 或 fallback 信号，不完全是无痕失败；但它们没有达到
TCFD `ReportExtraction(successes, failures)` 那种所有批次都统一、强类型区分空成功和调用
失败的程度。

#### async/sync 边界仍有桥接

`src/ai/runtime_adapter.py::run_awaitable_sync` 在已有 event loop 中启动线程并同步 join，
用于兼容仍为同步协议的调用方。TCFD 的新 workflow 是端到端 async。FinRisk 已删除旧 LLM
runtime，但这层同步 adapter 说明应用接口还不是纯 async。

## 6. Chapter 4：迁移全部模型任务并编排程序化工作流

### 6.1 TCFD 定义了什么

教程文件：`frequency_analyzer/tutorials/04-programmatic-workflow.md`。

TCFD 规定“一个 Agent 只完成一个模型任务，workflow 决定先后顺序、并发、失败和数据
传递，Agent 不互相调用”。最终有五类 Agent：

| Agent | 输入/Deps | Typed output | 职责 |
| --- | --- | --- | --- |
| keyword | chunk + lexicon | `TCFDKeywords` | 四维关键词抽取 |
| relevance | cooccurrence context | `RelevanceDecision` | 判断共现是否有 TCFD 语义 |
| summary | deterministic stats + samples | `EvaluationSummary` | 只写叙述，不重算统计数字 |
| lexicon | candidates | `LexiconReview` | 接受/拒绝候选并确定维度 |
| label | cluster | `ClusterLabel` | 给关键词 cluster 命名 |

程序化 workflow：

- `workflows/extraction.py`：批量关键词抽取；
- `workflows/evaluation.py`：批量相关性判断，调用
  `analytics/statistics.py::compute_summary_stats` 计算数字，再调用 summary Agent；
- `workflows/lexicon.py`：批量审核 candidate，再用纯函数生成 reviewed lexicon；
- `workflows/clustering.py`：批量给 cluster 命名；
- `main.py`：唯一 CLI composition root，构造 model/agents/workflows/I/O。

### 6.2 TCFD 五个任务在 FinRisk 中的对应关系

| TCFD 任务 | FinRisk 对应 | 是否直接等价 |
| --- | --- | --- |
| keyword extraction | `build_filing_extraction_agent`、`build_generic_extraction_agent` | 架构等价，业务 schema 不同 |
| relevance decision | `build_market_research_agent` 加 evidence/claim grounding validators | 职责被拆成模型研究与确定性证据校验，不是一对一 Agent |
| narrative summary | `ReportGeneratorStep`，另有 browser `PageSummary` Agent | 最终报告刻意由确定性代码生成；browser summary 只服务单页 |
| lexicon review | 无 | FinRisk 当前不维护 TCFD 词袋，不应把 supplier review 冒充为同一功能 |
| cluster label | 无直接实现 | node profile 和 lifecycle classification 是相邻能力，但不是关键词聚类命名 |

FinRisk 自己增加了 TCFD 没有的模型任务：

- planner：决定 subgoal、tool scope、tool selection 和 stop；
- market research：使用受限工具生成 source-backed research output；
- browser explorer：在 step/request 限制内选择受控浏览动作；
- supply-chain requirement decomposition；
- supplier hypothesis proposal；
- source-backed supplier relation extraction；
- supply-chain node profiling；
- filing、Web、transcript 的通用 entity/relation/claim/evidence extraction。

### 6.3 FinRisk 的三类 Pydantic Graph

#### FinRisk 九步图

`src/ai/graphs/finrisk.py::build_finrisk_graph` 按顺序定义：

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

每个 node 读取和更新 `FinRiskWorkflowState`。关键步骤遇到 blocker 后失败，非关键步骤可降级
继续；失败后的后续步骤会留下 skipped trace。`run_finrisk_graph` 是执行入口，
`run_finrisk_workflow` 只做公共兼容入口并委托给 Graph。

#### Supply Chain 九步图

`src/ai/graphs/supply_chain.py::build_supply_chain_graph` 定义：

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

Graph 还负责在开始、结束时写入 run store。typed supply-chain Agent 通过
`PydanticAISupplyChainClient` 被各业务 step 调用。

#### Global Agent 图

`src/ai/graphs/global_agent.py::build_global_agent_graph` 定义有界循环：

```text
initialize
  -> plan_next
  -> execute_subgoal
  -> plan_next
  -> ...
  -> finish
```

它检查 subgoal 数、总时长和总工具调用预算；执行失败、无工具证据、低置信度或需要人工
复核时，写入明确 stop reason、trace 和 review item。

### 6.4 哪些职责刻意保持确定性

FinRisk 没有把所有功能都改成 Agent：

- `src/workflows/steps/risk_scorer.py::compute_risk_score` 用明确权重计算风险分数；
- `src/workflows/steps/lifecycle_classifier.py` 用时间、证据重叠和反驳词判断 current、
  emerging、receding、unknown；
- `src/workflows/steps/report_generator.py` 从 typed state 渲染报告和证据表；
- `src/workflows/evaluation.py::evaluate_workflow_state` 确定性检查证据覆盖、金融建议、
  section、source diversity 和 hallucination risk；
- `src/evaluation/validators/` 负责 claim/evidence/source/financial safety 门禁；
- graph path 验证、evidence normalization 和 Sankey canonicalization 也留在 Python 层。

这与 TCFD “模型做语义判断，统计和聚合保留纯函数”的原则一致，但 FinRisk 的确定性层
更大，因为它承担金融安全、证据确认、图一致性和 API 稳定性。

### 6.5 composition root 的差异

TCFD 是 CLI 工具，因此 `main.py` 可以成为单一 composition root。FinRisk 同时提供 FastAPI、
CLI、后台 workflow、research cycle 和供应链 API，所以存在多个产品入口；它们共享同一
`model_factory`、typed client、Graph 和 workflow，而不是共享一个 CLI main。

FinRisk 已通过 `tests/test_import_all_modules.py` 防止旧 `src/llm/*`、旧 Agent runtime、直接
`chat.completions` 和手工 JSON client 重新进入 `src/`。不过少量面向旧测试或第三方 adapter
协议的兼容 helper 仍存在，不能把“旧 runtime 已删除”表述成“所有兼容代码都已删除”。

## 7. Chapter 5：离线测试、eval 与迁移完成门禁

### 7.1 TCFD 定义了什么

教程文件：`frequency_analyzer/tutorials/05-evals.md`。

TCFD 将“架构迁移完成”和“模型质量足够”分成两个问题：

- architecture tests 证明旧 SDK 边界和错误依赖方向没有回来；
- offline regression 和独立 live eval 证明输出质量、可靠性、latency 和 usage。

实际实现包括：

- `tests/conftest.py` 全局禁用真实请求；
- `TestModel` 做 contract test，`FunctionModel` 精确控制多轮 retry/failure；
- `evals/cases/*.jsonl` 为 keyword、relevance、lexicon 各提供 20 个 synthetic seed cases；
- `evals/metrics.py` 计算 normalized/exact match、四维及 micro/macro precision、recall、F1、
  empty-output accuracy 和 binary metrics；
- `evals/run_live.py` 小并发执行真实 Agent，分别统计 quality 与 reliability，保存 model、
  config、dataset/Agent revision、latency、usage、retry 和 failure category；
- `tests/architecture/test_boundaries.py` 用 AST 检查 domain/I/O/analytics/Agent 依赖方向、
  direct OpenAI import、旧符号、空成功模式和旧 sync/thread-pool 模式；
- `tests/integration/test_analysis_workflow.py` 用多个 `FunctionModel` 验证 retry、部分失败、
  deterministic stats 和 exporter round trip。

### 7.2 FinRisk 的离线测试门禁

FinRisk 已实现的对应能力：

| 文件 | 定义/检查 | 作用 |
| --- | --- | --- |
| `tests/conftest.py` | `models.ALLOW_MODEL_REQUESTS = False` | 默认全仓测试禁止真实模型请求 |
| `tests/ai/test_model_factory.py` | provider/config 工厂测试 | 验证四类 provider、覆盖和无意外 fallback |
| `tests/ai/test_structured_agents.py` | output contract 与 planner retry | 验证 relation evidence、empty filing 和 unauthorized scope |
| `tests/ai/test_research_agent.py` | grounding contract | 验证无证据不能 completed |
| `tests/ai/test_structured_clients.py` | production protocol | 验证 filing/supply chain/generic client 返回 typed output 和 audit rows |
| `tests/ai/test_toolsets.py` | typed schema、scope 和 execution check | 防止隐藏工具被直接绕过调用 |
| `tests/ai/graphs/test_finrisk_graph.py` | FinRisk graph parity | 验证 Graph 和原顺序 workflow 的状态、trace、风险、证据、评分和报告一致 |
| `tests/ai/graphs/test_supply_chain_graph.py` | Supply Chain parity | 验证 nodes、links、evidence、Sankey 和 evaluation 一致 |
| `tests/ai/graphs/test_parallel_policy.py` | 并行安全 | 拒绝 read/write 或 shared-write 冲突 |
| `tests/ai/graphs/test_reducers.py` | reducer | 验证合并稳定、幂等，失败分支不丢成功结果 |
| `tests/test_import_all_modules.py` | import/source gate | 所有 `src` 模块必须可导入；旧 runtime 文件和 direct SDK/JSON client token 不得出现 |

FinRisk 的默认测试和 live acceptance 也明确分开。`scripts/pydantic_ai_live_acceptance.py`
不是默认 pytest 的一部分。

### 7.3 FinRisk 的 eval 层

FinRisk 当前有三类离线 eval：

#### Workflow golden matrix

`eval/golden_cases.json` 有 30 个 case，覆盖 bank、biotech、energy、foreign issuer、
provider missing、restatement、SaaS、semiconductor、source conflict 等类别。

`eval/run_eval.py` 逐 case 执行 demo workflow，报告：

- final status；
- top-risk evidence coverage；
- financial-advice risk；
- unsupported claim count；
- schema validity；
- source diversity；
- hallucination risk；
- forbidden phrases。

`tests/evaluation/test_release_golden_matrix.py` 固定至少 30 个 unique case、证据要求和类别
覆盖。

#### Agent golden cases

`src/evaluation/agent_eval.py` 定义：

- `AgentGoldenCase`：goal、workflow kind、tool events、期待的工具族、证据接受/拒绝数量、
  是否需要 review 和禁止术语；
- `AgentGoldenResult`：tool choice、evidence discipline、stop/review、safety boundary 和
  final verdict；
- `evaluate_agent_golden_case`：从工具 trace 归一化 evidence candidate，并用确定性规则
  打分。

当前 `tests/fixtures/agent_golden_cases/` 有两个 case：Apple supply chain 和 insufficient
evidence review。

#### 组件级确定性指标

- `src/evaluation/extraction_eval.py::evaluate_extraction` 用 entity/relation ID overlap 计算
  matched count、unsupported claims 和 evidence coverage；
- `src/evaluation/report_eval.py::evaluate_report` 检查 citation marker、免责声明、
  counter-evidence section 和禁止措辞；
- `src/evaluation/metrics/` 计算 source diversity 和 hallucination risk；
- `src/evaluation/validators/` 提供运行时 guardrail，与 release eval 共用业务规则。

### 7.4 FinRisk 与 TCFD Chapter 5 的差距

#### Golden matrix 不是模型任务的人工标注集

`eval/run_eval.py` 当前让所有 case 共享同一个 AAPL demo fixture，并明确只断言 guardrail 和
禁止措辞，不断言精确风险标签。因此 30 个 case 更像 workflow contract matrix，不等价于
TCFD keyword/relevance/lexicon 的逐样本 gold label。

#### 抽取指标没有完整 precision/recall/F1

`evaluate_extraction` 目前计算 exact ID overlap 和总体 evidence coverage，没有分别报告
entity/relation/claim 的 precision、recall、F1，也没有 micro/macro 或 normalized/exact 的
对照。它不能直接替代 TCFD 的 extraction metrics。

#### 缺少任务级 live quality eval runner

FinRisk 的 live acceptance 证明 provider 能完成 typed output、tool call 和 usage；
`docs/testing/real-data-acceptance.md` 说明如何验收真实数据链路。但当前没有等价于
`frequency_analyzer/evals/run_live.py` 的 runner，把真实 Agent prediction 与版本化 gold
label 比较，并保存 retry/failure/quality/latency 的不可覆盖历史报告。

#### 架构测试侧重点不同

`tests/test_import_all_modules.py` 很强地检查旧 runtime 文件、direct SDK 调用和旧符号不会
回归；但没有像 TCFD 那样用 AST 系统检查 domain、I/O、analytics、Agent、workflow 的全部
依赖方向，也没有扫描所有 Agent exception handler 是否伪造空成功。

因此 FinRisk 已有可靠的离线回归和迁移 source gate，但若按 TCFD Chapter 5 的严格定义，
“模型质量 eval 闭环”仍是部分完成。

## 8. 两个项目的最终架构对照

```text
TCFD
CLI
  -> programmatic workflows
  -> five typed Agents
  -> one model factory
  -> small task-specific deps
  -> typed domain results / typed failures
  -> deterministic statistics and I/O

FinRisk
API / CLI / background workflows
  -> FinRisk Graph / Supply Chain Graph / Global Agent Graph
  -> typed specialist Agents and scoped toolsets
  -> one multi-provider model factory
  -> run-scoped deps + permissions + services + budgets
  -> evidence normalization and public workflow state
  -> deterministic scoring / lifecycle / graph validation / report
  -> guardrails / human review / trace / persistence
```

TCFD 的优势是小、纯、教学边界完整，尤其是 async concurrency、typed failure 和任务级 live
eval。FinRisk 的优势是生产治理更完整：多 provider、per-run 配置、权限双检、工具 trace、
预算、消息恢复、Graph、证据链、质量门禁和人工复核。

## 9. 面试时应该如何准确介绍

可以用下面这段作为两分钟版本：

> 我先在一个 TCFD 文本分析项目里用 0–5 章验证 Pydantic AI 的核心模式：集中式模型工厂、
> typed output、run-scoped dependencies、output validator、程序化 workflow，以及离线和
> live eval。然后我把这些模式应用到更复杂的 FinRisk 系统，但没有照搬关键词业务。
> FinRisk 用一个 model factory 接入 SGLang、vLLM、DeepSeek 和 OpenAI，用 typed Agent
> 处理 filing、research、planner、browser 和 supply-chain 任务；用 AgentDeps 注入权限、
> 工具、预算、消息和 trace；再由三类 Pydantic Graph 编排。模型负责结构化抽取、研究和
> 工具选择，评分、证据确认、图验证、报告和金融安全规则保持确定性。默认测试禁止真实
> 模型请求，生产路径有 typed trace、fallback、needs-review 和 source gate。

如果面试官继续追问，应主动说明边界：

- FinRisk 没有实现 TCFD 的 lexicon review 和 cluster label，因为它们不属于当前业务；
- FinRisk 的 dynamic behavior 主要是权限化 toolset，不是 dynamic system instructions；
- filing chunk 当前顺序调用，没有 TCFD 那种 semaphore 并发；
- 现有 30-case eval 主要证明 workflow/guardrail 合同，还不是充分的模型质量 benchmark；
- 少量兼容 helper 和空结果加 warning 的路径仍值得进一步统一为 typed failure。

这种说法比“我把 Tutorial 0–5 全部搬进 FinRisk”更准确，也更能体现你理解了架构取舍、
生产约束和未完成项。

## 10. 若要让 FinRisk 完整达到 TCFD 0–5 的严格标准

建议按以下优先级补齐：

1. 把 `timeout_s` 真正接入 model/provider HTTP client，并增加 timeout/retry 工厂测试；
2. 将 live acceptance 拆成 plain、native、prompted、tool calling 四项 capability 结果；
3. 为 filing chunk 增加有界 async concurrency，或写 ADR 明确为何保持顺序执行；
4. 定义统一的 `ChunkSuccess/ChunkFailure/BatchExtractionReport`，删除空对象加 warning 的
   模糊失败路径；
5. 清理 filing step 中剩余的 `hasattr`、single-shot 和旧私有 helper 兼容分支；
6. 建立 filing risk、supplier relation、research grounding 的版本化 gold dataset；
7. 补齐 task-level precision/recall/F1、empty-output accuracy、retry/failure/latency/usage；
8. 增加 timestamped、不可覆盖的 live quality eval runner；
9. 增加 AST dependency-direction tests 和“异常不能伪造空成功”的 source gate。

完成这些项目后，FinRisk 不仅拥有比 TCFD 更丰富的生产能力，也能在 Chapter 0–5 所强调的
边界纯度、失败语义和可量化模型质量上达到同等严格程度。
