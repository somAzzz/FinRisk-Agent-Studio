# FinRisk 项目全景与面试讲法

本文回答三个问题：FinRisk 现在能做什么、核心能力是怎么实现的、面试时应该怎样准确地介绍。内容以当前代码为准，不把路线图能力、静态 fixture 或外部服务能力说成已经在线生产。

## 1. 一句话定义

FinRisk Agent Studio 是一个面向个人金融研究的 evidence-first 工作台：它把 SEC 文件、财务事实、电话会、网页与图谱证据组织成可追溯的风险研究结果，再通过确定性质量门禁和人工复核把“模型生成内容”变成“可以检查的研究过程”。

它解决的核心问题不是“让 LLM 写一篇更长的报告”，而是：

1. 每个重要结论来自哪里，能否回到原始证据？
2. 数据在什么时间点已知，是否污染了历史判断？
3. 模型、规则和用户输入各自负责什么，是否被混成了事实？
4. 外部数据或模型失败时，系统是明确降级，还是悄悄编造完整结果？
5. 哪些结果可以自动接受，哪些必须交给分析师复核？

## 2. 当前已经实现的功能

| 产品能力 | 用户得到什么 | 主要实现位置 |
| --- | --- | --- |
| FinRisk 风险工作流 | 从公司和研究目标出发，得到风险、证据、评分、图路径、报告和质量结论 | `src/workflows/`、`src/ai/graphs/finrisk.py` |
| 数据与证据采集 | SEC/EDGAR、filing section、XBRL、transcript、搜索、网页和浏览器结果 | `src/data/`、`src/tools/`、`src/browser/` |
| 质量门禁 | schema、证据覆盖、claim grounding、来源质量、财务安全、报告结构与 fallback 检查 | `src/evaluation/`、`src/workflows/quality_gate.py` |
| 图推理 | 检索候选路径、评分、绑定证据、解释并验证图洞察 | `src/graph_reasoning/`、`src/graph/` |
| 供应链研究 | 产品需求拆解、供应商发现、递归扩展、Sankey 和图投影 | `src/supply_chain/` |
| Agent Runs | 受预算和权限约束的工具调用、trace、候选证据、人工审批与恢复 | `src/agents/`、`src/ai/`、`src/api/agent_runs.py` |
| 个人研究闭环 | 不可变快照、变化检测、Thesis、Watchlist、Expectation、Alert 和财报后复盘 | `src/research/`、`src/api/research.py` |
| 财务事实 | 行业指标模板、restatement 语义、单季/TTM 派生和来源 lineage | `src/research/financial_snapshot.py`、`config/financial_metrics/` |
| 同行与估值 | 同行组、分层比较、情景/敏感性、倍数和简化 DCF，保留假设历史 | `src/research/comparison.py`、`peer_groups.py`、`valuation.py` |
| 监控 | Watchlist 增量扫描、重试/节流、去重提醒和本地调度模板 | `src/research/monitor.py`、`deploy/` |
| Web 工作台 | Today、Company、Research Runs、Journal，多状态和桌面/移动界面 | `frontend/src/` |
| API 与存储 | FastAPI 后台任务、运行查询、SQLite 持久化、迁移/备份/恢复 | `src/api/`、`src/research/database.py` |

### 2.1 FinRisk 主工作流

当前主链路有九步：

```text
Company Resolver
→ Filing Risk Extraction
→ Market Evidence Collection
→ Evidence Normalization
→ Risk Scoring
→ Risk Lifecycle Classification
→ Graph Reasoning
→ Structured Report Generation
→ Evaluation / Human Review Gate
```

- Company Resolver 统一 ticker、CIK、公司名称等身份信息。
- Filing Risk Extraction 从申报文件中抽取结构化风险，并保留 chunk、section 和模型调用记录。
- Market Evidence Collection 通过 scoped tools 补充新闻、网页和市场侧证据。
- Evidence Normalization 将异构结果变成稳定 ID、来源、时间、引用和置信度一致的 evidence。
- Risk Scoring 使用确定性规则生成可解释的分项与总分，不让 LLM 直接给最终风险分。
- Lifecycle Classification 标记风险是新增、持续、升级、缓解还是信息不足。
- Graph Reasoning 只解释已经检索并绑定证据的路径。
- Report Generation 从结构化 state 渲染报告和证据表。
- Evaluation 汇总质量 findings，得到 `completed`、`needs_review` 或 `failed`。

编排使用 Pydantic Graph，但公共状态仍是 `FinRiskWorkflowState`。API、CLI 和后台任务共享同一入口，避免出现三套稍有不同的业务流程。

### 2.2 Evidence-first 的实现

系统没有把“模型回答”直接当成最终事实，而是分层处理：

```text
Provider raw result
→ typed output / tool result
→ evidence candidate
→ normalization + provenance
→ deterministic validation
→ confirmed state 或 human review
→ claim / report / graph projection
```

关键字段包括 source/source ID、observed/published/retrieved time、`as_of`、evidence type、lineage、component status 和 review status。reported、derived、provider、user-entered 与 model interpretation 保持不同语义。

这套设计带来两个重要结果：第一，可以从报告结论反查 evidence ID 和来源；第二，某个 provider 缺失时，系统会标记 `unavailable` 或 `partial`，不会把“没取到数据”解释为“风险不存在”。

### 2.3 LLM 与确定性代码的边界

Pydantic AI 是唯一的模型运行时，集中负责：

- provider/model 构造和 OpenAI-compatible 接入；
- typed dependencies、structured output 和 typed tools；
- 消息协议、usage 以及模型调用记录；
- 市场研究、浏览器动作选择、filing 风险和供应商关系等适合模型处理的任务。

项目代码继续负责：

- 权限、预算、审批、SSRF 与敏感信息脱敏；
- evidence 确认、risk scoring、graph validation 和 report safety；
- run store、幂等、恢复、业务状态机和 API 合同；
- cached/fixture/确定性降级。

这样的边界比“所有步骤都做成 Agent”更可控。模型处理开放语义，Python 处理不可绕过的不变量。

### 2.4 工具调用、权限和可观测性

工具通过 `ProjectTool` / `ToolCatalog` 注册，并带有 scope、risk level、evidence kind、参数 schema 和单次结果上限。当前 catalog 注册了 13 个模型可见工具，覆盖 Web、SEC filing、transcript、financial metrics/XBRL、graph path 和受限 browser exploration。默认工具以 `read_only` 为主；`browser_explore` 是 `interactive`，当前正式 catalog 没有实际的 `write_gated` 工具。

一次真实调用的控制链路是：

```text
用户目标
→ Planner 拆分 subgoal，并选择 tool scope
→ FilteredToolset 只向模型暴露当前 run 可见的工具
→ Pydantic AI 校验 typed arguments，模型选择具体工具
→ _invoke_project_tool 在执行前再次检查权限
→ ProjectTool 执行并包装为统一 result envelope
→ 记录 ToolExecutionEvent
→ EvidenceCandidateNormalizer 生成 evidence candidate
→ accepted / rejected / needs_review
```

这里有两个重要边界。第一，planner 主要决定“下一步研究什么、允许使用哪个工具域”，具体函数由模型在可见集合中选择；第二，工具是否可见和是否可执行是两次独立检查，因此不能只靠 system prompt 约束权限。图工具只接受实体、hop 和 edge type 等结构化参数，不接受 raw Cypher；上层 browser tool 只接受目标、初始 URL、最大步数和超时，不直接暴露 click/type/selector。

每个工具返回稳定 envelope：`tool`、`status`、`data`、`evidence_kind`、`warnings`、`truncated` 和 `error`。调用异常不会作为未处理异常直接喂给模型，而是变成可审计的 failed envelope 和 trace event。单工具输出由 `ProjectTool.max_result_chars` 截断；Pydantic AI `UsageLimits` 强制 request/tool-call 数量。

每次运行记录：

- planner/subgoal 和状态转换；
- tool name、参数摘要、结果 envelope、耗时和错误；
- provider/model、token usage 和 fallback；
- evidence candidate 的接受/拒绝；
- human review 与 deferred approval；
- run ID、conversation ID 和 parent run 关联。

消息以版本化 append-only batch 保存。resume 从服务端恢复历史并创建新的 run ID，operation ID 防止消息重复追加。项目还实现了 deferred approval store：审批带 TTL 和单次 token，SQLite 版本用事务保证并发下只有一个 worker 可以领取，并拒绝 replay。不过这套审批基础设施目前主要通过单元测试验证，尚不能描述为已经接入大量真实写操作；默认 Agent API 仍显式设置 `allow_interactive=False`、`allow_write=False`。

### 2.5 质量门禁为什么不是一次“打分”

质量层按步骤运行多个独立 validator，而不是让另一个 LLM 主观评价：

- Schema：状态和输出是否满足 Pydantic 合同；
- Evidence：每个风险是否有有效证据；
- Claim grounding：报告 claim 是否映射到 evidence；
- Source quality：来源可信度、时效性和多样性；
- Financial safety：是否出现禁用的买卖建议或过度确定表达；
- Report structure：必要章节、证据表和免责声明是否完整；
- Workflow：步骤、trace、fallback 和终态是否一致；
- Graph：路径和边是否有对应证据。

设计目标是：critical step 的 blocker 使工作流失败；非关键的市场或图步骤可以继续生成有限结果，同时保留 finding 并进入人工复核。这样“技术执行失败”和“研究完成但需要判断”是不同状态。当前代码仍同时保留旧版 `state.evaluation` 和新版 `state.workflow_evaluation`，两个口径在个别路径上可能不一致；这属于 v0.1 候选需要收敛的兼容性债务，不能在面试中说成已经完全统一。

### 2.6 图推理与供应链

图推理采用受控流水线：

```text
Context Builder
→ Candidate Path Retriever
→ Path Scorer
→ Evidence Binder
→ Path Interpreter
→ Insight Validator
```

LLM 只能解释已有候选路径，不能直接写 confirmed edge。没有 evidence ID 的关系保留为 hypothesis/candidate，或被拒绝。

供应链工作流沿用同一原则：先拆解产品需求，再搜索和抽取供应商候选，归一化节点与边，递归扩展，生成 Sankey，最后执行质量评估和可选图投影。它特别处理别名合并、循环、重复边、无证据关系和扩展边界，避免生成一张“看起来丰富但不可验证”的图。

### 2.7 Point-in-time 个人研究闭环

FinRisk 的输出可以进入研究闭环：

```text
Workflow Run
→ immutable CompanyResearchSnapshot
→ snapshot diff / ResearchChange
→ analyst review
→ Expectation + Valuation + Thesis
→ Watchlist scan + deduplicated Alert
→ Post-earnings Review
```

快照创建后不可被新数据覆盖；`as_of` 之后的 filing、amendment 或预期修订不能回写旧快照。变化检测保留 before/after、evidence IDs、materiality 和 review status。这样才能复盘“当时基于什么信息做了什么判断”，而不是用后来数据美化过去结论。

### 2.8 财务、同行和估值

财务层用配置驱动的指标别名支持 general、bank、biotech、energy、SaaS 和 semiconductor 模板。事实保留 original、amended、latest-known 三种查询语义，并对单季值、TTM、FCF 等派生值记录公式和输入 lineage。

同行分析不生成一个不可解释的综合神奇分数，而是分开展示财务、风险、预期和估值。系统对 fiscal period、币种、新鲜度和缺失值做显式处理，SEC SIC 候选仍需分析师确认。

估值包括：

- scenario valuation；
- sensitivity matrix；
- P/E、EV/EBITDA、FCF yield；
- 简化 DCF；
- 不可变的 assumption history。

估值结果是研究工具，不是买卖建议；用户假设不会被标记为 reported fact。

### 2.9 前端、API、存储和部署

FastAPI 提供四组主要边界：`/workflows`、`/supply-chain`、`/agent-runs` 和 `/research`。长任务先返回 run ID，再通过状态、timeline、report、trace、graph、evaluation 和 artifacts 接口查看结果。

React/Vite 工作台按用户任务组织为 Today、Company、Research Runs 和 Journal，而不是按内部 Agent 名称组织。页面区分 loading、empty、partial、failed 和 needs-review；静态 GitHub Pages 明确使用 offline fixture。

Research Snapshot 与 Journal 默认使用 SQLite，并支持 schema migration、事务、备份和恢复。Neo4j 是可选图后端；SGLang/vLLM 等模型服务在仓库外管理。本地 demo 和 CI 不要求 GPU、密钥或实时网络。

## 3. 这个项目最值得讲的技术点

### 3.1 从“生成答案”改成“管理证据状态”

项目的核心抽象不是 prompt，而是 typed workflow state、evidence lifecycle 和 quality gate。LLM 只是证据生产链中的一个可替换组件。这个取舍让系统更容易测试、回放、降级和人工复核。

### 3.2 把非确定性限制在合适位置

开放式搜索、语义抽取和路径解释交给模型；身份解析、分数、时间边界、证据确认、权限与终态交给确定性代码。面试时可以把这概括为：

> 我不是追求 Agent 自治程度最大化，而是追求在可审计约束内，把模型用在规则最难覆盖的部分。

### 3.3 失败语义是一等公民

系统区分 failed、unavailable、partial、needs_review 和 completed，也记录从 live 到 cached/demo 的 fallback。金融研究里，“没有数据”“调用失败”“没有风险”和“证据不足”绝不能是同一件事。

### 3.4 Point-in-time 防止 hindsight bias

快照、amendment、expectation 和 source cursor 都带时间语义。这个设计既是数据工程问题，也是金融研究方法问题：只有保留当时可见信息，复盘和监控才有意义。

### 3.5 同一业务合同支持 demo、cached 和 live

不同运行模式复用相同 Pydantic state 和 API payload，区别通过 provenance、component status 和 fallback event 显式表达。demo 可以稳定演示，但不会冒充实时结果。

### 3.6 Tool calling 的面试主线

这个项目的工具系统不是“把若干 Python 函数交给模型”，而是把工具当作带治理元数据的能力对象。可以按四层解释：

1. **注册层**：`src/tools/contracts.py` 定义 `ProjectTool`，将 schema、scope、风险等级、证据类型和返回大小绑定在一起；`src/tools/catalog.py` 注册具体工具并隐藏搜索 provider 等底层差异。
2. **暴露层**：`src/ai/toolsets.py` 将 catalog 转成 Pydantic AI typed tool，并用 `FilteredToolset` 根据每个 run 的 `AgentPermissions` 动态过滤。
3. **执行层**：`_invoke_project_tool` 再做一次权限检查，通过 `asyncio.to_thread` 调用同步 provider，统一处理异常、envelope、延迟、错误和 trace。
4. **证据层**：`src/evidence/candidates.py` 不把成功的 tool result 直接当事实，而是拆成来源可追踪的候选证据，再根据来源质量和 grounding 决定接受、拒绝或复核。

面试时最值得强调的一句话是：

> Tool success 只说明调用成功，不说明返回内容已经被研究系统接受为事实。

预算也要准确讲。当前已强制的是每个 subgoal 的 request/tool-call 数量、全局 subgoal 数量和总运行时间；外层 Graph 在每个 subgoal 完成后检查累计 tool-call 数量，每个工具还有独立的返回长度截断。`max_total_fetch_pages` 尚未接入全局执行计数，`max_total_tool_result_chars` 当前主要记录 usage，尚未作为跨工具硬中断条件。

### 3.7 Guardrails 的分层模型

Guardrail 可以分为两类：

- **Preventive guardrails**：调用前缩小能力面，例如 typed parameters、scope、risk level、最大 hop、最大 page、timeout、SSRF 和禁止 raw Cypher。
- **Detective / corrective guardrails**：调用后检查结果，例如 evidence linkage、claim grounding、source quality、report safety、graph path validation、memory downgrade 和 human review。

当前代码形成五层防线：

| 层级 | 主要约束 | 代表实现 |
| --- | --- | --- |
| Schema | Pydantic 类型、范围、必要字段 | `src/schemas/`、`SchemaValidator` |
| Tool | scope、risk、参数上限、二次鉴权、SSRF、截断 | `src/tools/`、`src/ai/toolsets.py`、`src/security/url_guard.py` |
| Evidence | candidate lifecycle、risk/claim/evidence lineage、来源质量 | `src/evidence/`、`ClaimGroundingValidator`、`EvidenceValidator` |
| Output | 报告章节、免责声明、投资建议语言 | `ReportStructureValidator`、`FinancialSafetyValidator` |
| Workflow/Memory | blocker、fallback、人工复核、candidate/active memory | `GuardrailEngine`、`src/evaluation/memory_guardrails.py` |

`GuardrailEngine` 的一个可靠性设计是 validator 本身抛异常时不会静默跳过，而是转换成 blocker finding，使 trace 仍能解释质量层为什么失败。需要注意：prompt injection 在当前实现中并未被“彻底解决”；现有策略主要是限制 blast radius——默认无写权限、图工具无 raw Cypher、上层不暴露低级浏览器动作、Web fetch 有 SSRF、防止工具无限调用，并要求结果经过证据层。

### 3.8 Evals 的分层模型

面试时先区分 eval 和 guardrail：

> Guardrail 决定一次运行能否继续、发布或转人工；eval 用于比较系统版本、发现退化和校准阈值。两者可以复用信号，但职责不同。

当前评测分为四层：

| 层级 | 评什么 | 主要实现 |
| --- | --- | --- |
| 单元/合同 | schema、权限过滤、tool envelope、SSRF、审批过期与 replay | `tests/ai/`、`tests/tools/`、`tests/security/` |
| 组件 | extraction coverage、claim grounding、source diversity、graph consistency、report structure | `src/evaluation/` |
| Agent golden trace | tool family、候选证据纪律、stop/review、安全边界 | `src/evaluation/agent_eval.py` |
| Live acceptance | 真实 provider 的 structured output、tool calling 和工作流兼容性 | `scripts/*live_acceptance.py` |

主要确定性指标包括：

- `evidence_coverage`：有证据关联的风险或实体/关系占比；
- `hallucination_risk`：无证据 top risk 比例与错误 claim 引用比例中的较大值；
- `source_diversity`：唯一来源域数量除以 evidence 数量；
- `claim grounding`：先检查 evidence ID 和 risk lineage，再计算词法 overlap；
- `tool_choice_score`：预期工具族被实际 tool trace 覆盖的比例；
- `evidence_discipline_score`：accepted/rejected candidate 是否符合 golden case 预期；
- `stop_review_score`：证据不足时是否正确进入复核，而不是继续输出确定结论。

词法 overlap 是一个便宜、可重复的 CI baseline，不是事实正确性的最终证明。它擅长抓空引用、错误 ID 和明显不相关文本，但可能漏掉同义改写，也可能接受关键词重合但语义矛盾的内容。合理的后续方案是增加人工标注集和 NLI/LLM judge，并与确定性 Layer 1 校验组合，而不是用 judge 替代全部规则。

### 3.9 当前 eval 结果应该怎样准确表述

2026-09-07 针对 evaluation、typed tools、usage、deferred approval、tool contracts、quality-gated workflow 和 SSRF 的聚焦复核结果为 `119 passed`；`eval/run_eval.py` 当前输出 30/30 pass。

但 30 个 case 不能称为“30 家公司的真实模型 benchmark”：

- runner 当前让所有 case 共享同一份 AAPL demo fixture；
- `expected_risk_types` 和 `must_have_evidence` 没有参与最终 verdict；
- `should_not_contain` 虽然被扫描并写入结果，但 `forbidden_phrases_found` 没有参与退出码；
- runner 验证的是稳定的 workflow/guardrail contract，而不是每家公司风险识别的真实 precision/recall。

准确说法是：

> 当前有 30 个离线 guardrail 场景用于验证合同、证据覆盖和安全回归；真实跨公司效果 benchmark 仍需要独立 fixture、标注期望和版本对比。

## 4. 面试时怎么介绍

不要从功能列表开始。推荐时间分配是：tool calling 与可观测性约 40%，runtime guardrails 约 35%，evals 约 20%，前端/API/存储约 5%。如果岗位偏数据或金融研究，再把 point-in-time 和 financial reconciliation 提到主线。

### 4.1 30 秒版本

> 我做了一个 evidence-first 的金融研究 Agent 工作台。它会从 SEC 文件、财务事实、电话会和网页中提取风险证据，经过九步 Pydantic Graph 工作流完成归一化、确定性评分、图推理、报告和质量门禁。和普通 RAG demo 不同，我重点解决了证据 lineage、point-in-time、失败降级和人工复核：每个结论能回源，模型不能直接创建确认图边或给买卖建议，证据不足会进入 needs-review。后面我又把结果接成了快照、预期、估值、Watchlist 和财报复盘闭环，并做了 FastAPI、React、SQLite/Neo4j 以及可离线演示的完整产品形态。

### 4.2 两分钟版本

可以按“问题—方案—难点—结果”讲：

> 金融研究 Agent 的难点不是生成一篇报告，而是如何证明报告中的事实来自哪里、在什么时间已知，以及外部服务失败时系统有没有误导用户。为此我把系统设计成 evidence-first workflow，而不是聊天机器人。
>
> 后端用 FastAPI，核心研究链路用 Pydantic Graph 编排九个步骤，公共状态全部用 Pydantic model。Pydantic AI 负责 typed output 和受限工具调用，规则代码负责 evidence confirmation、风险评分、图路径验证、权限、预算和质量门禁。Planner 先选择研究 subgoal 和工具 scope，模型只能在授权工具集合中选择具体函数；执行时还会再次检查权限，并把结果统一写入 trace。
>
> 工具调用成功以后，结果也不会直接成为事实，而是先转换成 evidence candidate，再根据来源质量、grounding 和引用完整性进入 accepted、rejected 或 needs-review。Guardrail 分为调用前的权限、参数、SSRF 和预算控制，以及调用后的 schema、claim grounding、来源质量、报告安全和图路径验证。证据不足时系统进入 needs-review，不把“工具失败”误解为“没有风险”。
>
> Eval 采用分层策略：底层测试 schema、tool contract 和安全边界；中间层测试 evidence 与 workflow guardrails；上层通过 golden tool trace 评估工具族选择、证据纪律和停止/复核策略，真实 provider 再走独立 live acceptance。产品上还包括供应链 Sankey、研究快照、估值、Watchlist 和财报复盘。这个项目让我真正处理了 Agent 系统的可审计性、可靠性和产品化，而不只是 prompt engineering。

### 4.3 深挖时推荐讲的四个故事

#### 故事一：为什么没有让 LLM 直接评分

- 情境：风险抽取可以用模型，但最终分数若由模型直接产生，难以解释和回归。
- 决策：模型输出结构化风险与证据；Python 根据可见字段计算分项和总分。
- 结果：同一输入可重复得到同一评分，测试可以覆盖边界条件，报告仍可展示评分依据。
- 取舍：规则不如模型灵活，但适合最终排序；语义理解仍放在上游模型步骤。

#### 故事二：provider 失败不能伪装成业务结论

- 情境：搜索、transcript、Neo4j 或 LLM 都可能因为密钥、网络和兼容性失败。
- 决策：每个 component 有独立 status，fallback 写入 trace，非关键步骤可继续但终态进入复核。
- 结果：用户仍能获得有限结果，同时知道缺了什么；demo/cached 也不会被标为 live。
- 取舍：状态模型和前端变复杂，但避免金融场景中最危险的“静默成功”。

#### 故事三：如何迁移到单一 Agent runtime

- 情境：早期存在自定义 tool loop、provider client 和业务编排重复，长期会造成两套语义。
- 决策：用集中式 model factory、typed tools、Pydantic AI 和 Pydantic Graph 逐路径迁移，完成后删除旧 runtime，而不是永久保留 feature flag。
- 结果：provider、消息、usage 和 structured output 统一，业务的 evidence/guardrail/API 合同保持稳定。
- 取舍：迁移期间需要 parity test 和 source/import gate；最终维护成本显著低于双 runtime。

#### 故事四：为什么工具结果还要经过 evidence candidate

- 情境：搜索返回 HTTP 200 或 tool status=success，并不代表内容可信、相关或足以支持结论。
- 决策：先把不同工具结果归一化为统一 candidate，计算来源质量和 grounding，再赋予 accepted、rejected 或 needs-review 状态。
- 结果：模型不能仅凭一次成功调用把数据写成确认事实；每条候选可以回到 tool event 和来源 URL。
- 取舍：启发式来源分与词法 grounding 不能替代语义真值，需要用真实标注继续校准。

### 4.4 常见追问与回答要点

**为什么不用纯 RAG？**  RAG 解决召回和上下文问题，但不能自动解决证据生命周期、时间边界、权限、业务状态和发布门禁。FinRisk 把 RAG/搜索作为证据采集的一环，而不是整个系统。

**怎么降低幻觉？**  typed output 只解决结构，不保证事实正确；因此还需要 source/quote 校验、evidence ID、claim grounding、图路径验证、来源质量、确定性报告规则和 human review。

**谁决定调用哪个工具？**  Planner 决定 subgoal 和 tool scope；Pydantic AI 模型在当前可见集合里选择具体工具并生成 typed arguments；runtime 在执行点再次授权。模型负责选择，系统负责限定选择空间和最终执行权。

**Tool call 成功是否等于证据可用？**  不等于。成功结果还要经过 `EvidenceCandidateNormalizer`；缺 URL、内容为空、来源质量过低或 grounding 不足会被拒绝或转人工复核。

**工具失败或者返回太大怎么办？**  异常会变成 failed envelope 和 `ToolExecutionEvent`，不会丢失审计信息；单工具结果按 `max_result_chars` 截断。没有 accepted evidence 的 subgoal 会创建 human-review item，而不是继续输出确定结论。

**如何防止 Agent 无限调用？**  Pydantic AI `UsageLimits` 控制每个 subgoal 的 request 和 tool-call 数量，外层 Graph 控制 subgoal 数与总运行时间，并在 subgoal 结束后检查累计调用数。要主动说明总 fetch-page 与跨工具字符预算仍未全部成为硬门禁，累计调用也不是每次调用前按剩余额度扣减。

**如何防 prompt injection？**  当前不能声称完全防止，重点是减少影响面：默认无写权限、工具按 scope 暴露、执行点二次检查、图工具不接受 raw Cypher、上层 browser 不暴露低级动作、Web fetch 有 SSRF。外部内容仍应被当作不可信输入，后续还需要专门的内容级 injection eval。

**Guardrail 和 eval 有什么区别？**  Guardrail 是运行时策略，决定继续、失败或复核；eval 是离线/验收机制，用来比较版本和校准策略。项目让二者复用 evidence、trace 和 finding 数据，但不混为同一概念。

**为什么 claim grounding 不直接用 LLM judge？**  ID 存在性、lineage 和引用完整性适合确定性规则，便于 CI 和审计。词法 overlap 是便宜的第二层；LLM/NLI judge 应作为补充层，并用人工数据校准，而不是成为唯一裁判。

**30/30 golden cases 说明了什么？**  说明当前共享 fixture 下的 workflow contract 和已有安全规则没有回归；不说明 30 家公司的风险识别都正确，因为 case 尚未使用独立数据和完整期望判分。

**为什么有 `needs_review`，不能只有成功和失败？**  技术执行成功不等于证据充分。`needs_review` 表示产物可以检查，但来源、grounding、冲突或覆盖不足需要分析师判断；`failed` 表示关键不变量或关键步骤未满足。

**Deferred approval 如何防止重复执行？**  审批有 TTL 和随机 decision token；SQLite store 通过 `BEGIN IMMEDIATE` 原子领取，并把状态改成 executed，后续 replay 会被拒绝和审计。当前主要验证的是基础设施合同，正式 catalog 尚未接入真实 write tool。

**为什么同时用 Pydantic Graph 和普通 Python？**  Graph 表达可观察的业务状态转换；普通函数保留纯计算和 validator。不是每个函数都需要包装成 Agent 或节点。

**怎么测试 LLM 系统？**  分层测试 schema、tool、workflow、guardrail、golden case 和 live provider。离线 fixture 保证回归稳定，live acceptance 只验证真实 provider 能力，二者不能互相替代。

**如何支持多 provider？**  所有模型通过集中式 factory 构造。SGLang、vLLM、DeepSeek 走显式 OpenAI-compatible endpoint，OpenAI 走官方 provider；配置错误不静默换模型。

**为什么用 SQLite？**  当前定位是个人研究工作台，SQLite 部署简单、事务和备份能力足够，也方便做 point-in-time 本地数据。接口和 store 边界为以后替换后端留出了空间，但当前不夸大为多租户生产 SaaS。

**最大的未完成项是什么？**  长周期 Agent memory 的质量和过期策略、跨进程长任务恢复、更多真实 provider 集成矩阵、分部/consensus/FX 数据深度，以及发布 tag 和持续校准。

## 5. 面试演示建议

### 5.1 五分钟演示路径

1. 在 Today 或 Company 页面发起 AAPL 研究。
2. 打开 Research Runs，展示九步 timeline 和某次 tool trace。
3. 在 Risks 中选一个风险，沿 claim/evidence matrix 回到来源。
4. 打开 Evidence/Graph，说明 confirmed 与 candidate/hypothesis 的区别。
5. 展示 `needs_review`，解释它为何是研究状态而不是异常。
6. 在 Journal 创建 snapshot，比较 change，再展示 expectation 或 valuation assumption history。
7. 最后切到 Supply Chain Sankey，强调图边的证据要求。

如果现场没有网络、LLM 或 Neo4j，使用 static/demo fixture，并主动说明这是离线演示模式。不要把 fixture 说成实时数据。

### 5.2 代码讲解顺序

如果面试重点是 eval、tool calling 和 guardrails，推荐只打开少量关键文件：

1. `src/tools/contracts.py`：tool 为什么是带治理信息的能力对象；
2. `src/ai/toolsets.py`：typed wrapper、动态可见性、执行点二次鉴权和 trace；
3. `src/evidence/candidates.py`：tool result 为什么不能直接成为事实；
4. `src/ai/graphs/global_agent.py`：planner → subgoal → planner、预算和停止策略；
5. `src/evaluation/engine.py` 与 `src/workflows/v16_runner.py`：validator 如何进入 runtime 并聚合 verdict；
6. `src/evaluation/validators/claim_grounding_validator.py`：risk → claim → evidence 的实际校验；
7. `src/ai/approvals.py`：审批过期、单次 token、事务和 replay protection；
8. `eval/run_eval.py`：离线评测能证明什么、不能证明什么。

如果面试官继续问完整业务，再打开 `src/workflows/finrisk_workflow.py`、`src/graph_reasoning/subsystem.py` 和 `src/research/orchestrator.py`，分别解释九步工作流、受控图推理与 point-in-time snapshot。

不要逐目录念技术栈。面试官更关心的是你为何这样划分边界、失败时发生什么、如何证明它可靠。

## 6. 当前实现边界、已知债务与面试防守

### 6.1 产品与部署边界

- 当前是 `v0.1` release candidate；仓库没有产品 Git tag，不能说已正式发布 `v0.1.0`。
- GitHub Pages 是 static fixture dashboard，不是在线实时研究服务。
- 外部 SEC、transcript、search、LLM 和 Neo4j 的完整结果依赖网络、密钥或独立服务。
- 项目不是生产级多租户 SaaS，没有交易执行，也不输出买卖建议。
- Agent memory 已有模型和 guardrail 基础，但长期召回质量、过期和无人值守恢复仍在后续范围。
- 分部数据、外部 consensus、自动 FX 和通知 adapter 尚未成为默认完整能力。

### 6.2 Eval 和 guardrail 的代码级债务

以下问题是基于当前代码的真实审查结果。面试前最好优先修复；如果被问到，应作为已识别的工程债务说明，而不是回避。

1. **30 个 workflow golden case 仍共享 AAPL fixture。** `eval/run_eval.py` 为所有 case 构造不同 request，但传入同一个 fixture。`expected_risk_types` 和 `must_have_evidence` 没有进入 verdict；`forbidden_phrases_found` 被计算但不影响退出码。因此不能称为跨公司准确率 benchmark。
2. **v15/v16 双评测口径可能分歧。** API 主路径调用 `run_finrisk_workflow_v16`，但 state 同时保留 `evaluation` 与 `workflow_evaluation`。2026-09-07 的 AAPL demo 复核得到 `state.status=completed`、v15=`pass`、v16=`needs_review`。此外，graph subsystem 直接追加到 `state.guardrail_findings` 的 finding 不一定进入 `StepEvaluation`，而 workflow summary 的 blocker/warning count 只聚合 step evaluations。下一步应确定单一 canonical verdict，并让所有 finding 进入同一聚合路径，再让 API 和 UI 统一消费。
3. **severity 聚合遗漏 `ERROR`。** `GuardrailEngine._status_for()` 当前只识别 `BLOCKER` 和 `WARNING`；`FinancialSafetyValidator` 对 hard advice 生成 `severity=ERROR,status=FAIL`，可能在 v16 step summary 中被聚合成 pass。旧版 evaluator 仍会识别 hard advice，但双重实现加大了不一致风险。
4. **report-level evidence check 的 ID 比较不正确。** `EvidenceValidator` 先得到 evidence ID 集合，却直接判断 `risk.risk_id not in valid_ids`；正确逻辑应该检查 evidence 的 `related_risk_ids`。这会制造多余 warning。
5. **pre-step gate 目前不是严格 precondition。** `validate_pre_step()` 给所有 validator 传 `output=None`，`SchemaValidator` 会据此产生 blocker；runner 只记录日志并继续执行，而且 pre evaluation 没有追加到 state。应拆分 pre/post validator 或给 pre-step 单独的 state contract。
6. **部分预算字段只记录、未强制。** request/tool-call、subgoal 和总时间已执行；`max_total_fetch_pages` 未接入计数，`max_total_tool_result_chars` 目前主要进入 `ToolBudgetUsage`，没有跨工具中断。
7. **Deferred approval 尚未与真实 write tool 形成端到端路径。** denial、expiry、并发单次领取和 replay 已有测试，但当前 catalog 没有正式 write-gated 工具。
8. **Claim grounding 仍是启发式基线。** Layer 1 的 ID/lineage 检查价值很高；Layer 2 的英文词法 overlap 不适合作为多语言或复杂金融蕴含的最终判断，Layer 3 NLI/LLM judge 目前默认未启用。
9. **Trace summary 与 evidence ingestion 输入耦合。** `_invoke_project_tool` 把完整 envelope 截成 500 字符写入 `ToolExecutionEvent.result_summary`，而 `EvidenceCandidateNormalizer` 又从该字段反向解析证据。较大的 JSON 会被截成无效文本，目前只有部分 filing/Web 结果有 best-effort partial parser；更稳妥的设计是审计摘要与完整结构化 payload 分字段保存。
10. **部分已注册工具缺少 candidate row builder。** `management_snapshot_lookup` 和 `financial_snapshot_lookup` 在 catalog 中可调用，但 normalizer 的 `_rows_for_tool` 没有对应映射，成功调用可能最终得到“没有 source-backed evidence”的 rejected candidate。应补适配器或明确把它们定义为不直接产出 evidence 的辅助工具。

推荐的修复顺序是：统一 verdict、finding 汇总与 severity 聚合 → 分离 tool audit summary 和 evidence payload → 修复 evidence relation check 与缺失的 candidate adapter → 让 golden case 期望真正参与判分 → 接入累计预算 → 增加独立 fixture/真实标注 → 再扩展 write approval 和 semantic judge。

### 6.3 推荐说法与不推荐说法

| 不推荐 | 推荐 |
| --- | --- |
| “30 家公司 eval 全部通过” | “30 个离线 guardrail 场景通过；跨公司真实 benchmark 还在补独立 fixture 和标注” |
| “所有工具预算都有硬限制” | “调用次数和运行时间已强制，单工具结果会截断；累计页面和字符预算仍需补齐” |
| “写工具都有人工审批” | “已实现可恢复、防 replay 的审批基础设施，当前默认 catalog 没有真实写工具” |
| “系统解决了 prompt injection” | “通过最小权限、结构化工具和证据验证降低影响面，内容级 injection 仍需专项 eval” |
| “grounding 能证明事实正确” | “确定性检查能证明引用存在和 lineage 完整，语义支持度仍需要 judge 与人工标注” |
| “v0.1 已经生产可用” | “v0.1 release candidate 已形成完整产品闭环，发布门禁和长期运行能力仍在收尾” |

准确说明边界不会削弱项目，反而能体现你理解“代码能跑”“评测通过”和“生产可靠”之间的差距。

## 7. 未来规划：从受控检索升级为开放式问题发现

### 7.1 当前状态与目标边界

当前系统是“外层 workflow、内层 LLM”的混合架构，但整体仍偏 workflow-driven。`src/ai/graphs/finrisk.py` 固定九步主链路；`MarketExplorerStep` 会遍历 `state.filing_risks`，让模型围绕已经从财报识别出的风险调用工具和寻找市场证据。`/agent-runs` 的 `plan_next → execute_subgoal → plan_next` 循环更灵活，但 `AgentPlanner.initialize()` 仍会根据 workflow kind 注入默认 subgoal，执行空间主要由预设目标和 tool scope 决定。

因此当前系统擅长“为已知风险寻找证据”，但对下列未被财报风险抽取命中的问题发现能力有限：突发监管变化、客户流失、网络安全事件、竞争替代、管理层措辞异常，以及供应商所在地区的新事件。

未来目标不是取消 workflow、让模型无边界行动，而是采用 **bounded open-world discovery**：让 LLM 决定还应该调查什么，由确定性代码决定候选问题能否进入正式风险、评分和报告。

### 7.2 目标架构：开放发现 + 确定性验证

```text
固定初始化：公司解析、财报和基础快照
        │
        ├── 已知风险 workflow
        │
        └── 开放式问题发现循环
              Planner 动态提出假设/subgoal
                    ↕
              scoped read-only tools
                    ↕
              缺口、反证与新颖性检查
        │
        ▼
IssueCandidate 候选集合
        │
        ▼
来源、时间、实体、独立性、反证和去重验证
        │
        ▼
verified / rejected / needs_review
        │
        ▼
现有风险评分、报告、quality gate 和 eval
```

模型可以动态探索，但不能直接修改 confirmed evidence、最终风险分或发布状态。所有新发现先进入候选层，经过 evidence normalization 和 guardrail 后才能晋级。

计划增加类似下面的候选合同：

```python
class IssueCandidate:
    issue_id: str
    title: str
    hypothesis: str
    why_material: str
    why_novel: str
    supporting_evidence_ids: list[str]
    counter_evidence_ids: list[str]
    source_types: list[str]
    confidence: float
    materiality: float
    missing_checks: list[str]
    status: Literal["candidate", "verified", "rejected", "needs_review"]
```

风险 taxonomy 只作为探索提示，不作为封闭枚举；模型可以使用 `other + free_text_issue` 提出新类别。`risk_id=None` 的公司级市场证据也应先被保留为 candidate，再由实体/问题归类步骤关联已有风险或创建新候选风险，避免因为没有预先存在的 risk ID 而丢失发现。

### 7.3 Planner 和工具循环的代码演进

1. **加入 company-level discovery goal。** 除了 `MarketExplorerStep` 当前按 `filing_risks` 发起的定向研究，再运行一次不以已知风险为前提的公司级扫描，要求寻找重大变化、分析缺口和相互矛盾的信息。
2. **允许动态扩展 subgoal。** 调整 `AgentPlanner.initialize()`，保留必要的基础任务，但允许 LLM 根据当前 evidence manifest、已有风险、未覆盖来源、工具失败和剩余预算创建新 subgoal。
3. **补全 Graph 决策路由。** 在 `src/ai/graphs/global_agent.py` 中显式处理 `plan`、`call_tools`、`ask_review` 和 `stop`：`plan` 将新 subgoal 加入队列后继续规划，而不是因不是 `call_tools` 就结束运行。
4. **保持 scoped tool boundary。** 开放发现默认仍只使用只读工具；`FilteredToolset` 控制模型可见范围，执行点再次鉴权，浏览器、网络、调用次数、总时间和结果字符数继续受预算约束。
5. **加入 Explorer/Skeptic/Verifier 三阶段。** Explorer 提出候选问题；Skeptic 主动寻找反证、替代解释和转载依赖；Verifier 根据确定性合同决定进入 `verified`、`rejected` 或 `needs_review`。三个阶段可以由同一模型使用隔离 prompt 分别执行，不要求部署三个模型。
6. **增加明确停止条件。** 达到最大动态 subgoal 数、工具/时间/字符预算、连续多轮没有新证据、证据覆盖已满足，或出现高影响低置信度候选时停止或转人工复核。

Planner 不应接收无限增长的全文上下文，而应接收结构化摘要：已检查的文档和来源、已有风险、候选问题、支持/反对证据 ID、尚未覆盖的研究视角、工具错误和剩余预算。原始内容仍通过 evidence ID 按需取回。

### 7.4 开放发现的 guardrails

开放问题空间会提高召回率，也会提高误报和提示注入风险，因此候选晋级至少需要检查：

- 证据确实来自本次允许的 tool event，而不是模型自述；
- 公司实体、时间和 `as_of` 一致，不能把未来信息用于历史判断；
- 至少一个高质量一手来源，或多个相互独立的来源；
- 主动搜索反证，并记录没有找到反证还是没有执行检查；
- 与已有风险做语义、实体和时间维度的去重；
- “重大性”和“置信度”分开，重大但证据不足的候选进入 `needs_review`；
- 外部网页内容始终作为不可信数据，不得改变 system policy、tool scope 或审批条件；
- LLM 不能直接写 confirmed state、分数或最终报告结论。

### 7.5 对应的 eval 规划

开放发现不能只复用现有共享 fixture 的 workflow contract eval，需要单独建设人工标注数据集：

- **隐藏问题正样本：** 财报没有明确披露，但 transcript、XBRL 异常、监管文件或同期网页中存在可验证的重要问题；
- **已知风险样本：** 验证开放循环不会只重复 workflow 已有结论；
- **无新增问题负样本：** 防止模型为了表现“有发现”而制造风险；
- **矛盾和诱导样本：** 同时提供支持、反对证据、转载来源和 prompt injection 内容；
- **point-in-time 样本：** 加入在目标 `as_of` 之后才公开的信息，验证系统不会产生 hindsight leakage。

核心指标包括：

| 指标 | 回答的问题 |
| --- | --- |
| Novel Issue Recall | 人工标注的 workflow 外问题发现了多少 |
| False Discovery Rate | 新发现中有多少无法被证据支持 |
| Evidence-backed Novelty Rate | 候选是否既新颖又有可追溯证据 |
| Counter-evidence Coverage | 是否真正执行了反证搜索 |
| Source Independence | 多个来源是否只是同一内容的转载 |
| Promotion Accuracy | candidate 的 verified/rejected/needs_review 状态是否正确 |
| Budget Efficiency | 每个有效新问题消耗多少次调用、时间和 token |

评测时先冻结测试集和判分规则，再比较“现有 workflow baseline”“只增加开放 Planner”“开放 Planner + Skeptic/Verifier”。除了总体均值，还要按来源类型、行业和问题类型切片，并报告置信区间、失败案例和成本，不能只展示发现数量。

### 7.6 分阶段落地顺序

1. **Phase 1：观察模式。** 开放 discovery 只生成 `IssueCandidate` 和 trace，不进入现有风险状态或报告；使用人工标注评估 recall、误报和成本。
2. **Phase 2：人工复核模式。** 候选经过验证后进入 `needs_review`，由分析师决定是否晋级；校准来源、反证和重大性阈值。
3. **Phase 3：受控晋级。** 只有满足严格证据合同的候选可以自动进入正式风险，其余继续转人工；评分和最终报告仍走现有确定性 workflow。
4. **Phase 4：持续校准。** 用线上复核结果补充 eval 数据，监控行业漂移、来源质量、误报、预算和 provider 变化，版本化 prompt、模型、规则与数据集。

面试时可以概括为：

> 当前版本是 bounded agent：workflow 控制关键状态和发布门禁，LLM 在预设风险和工具范围内探索。下一阶段将增加开放式 issue discovery loop，让模型动态提出 workflow 未预设的研究假设；但新发现只能进入 candidate 状态，经过来源、时间、反证、独立性和去重验证后才能进入确定性评分和报告。这是在金融场景中同时提高未知风险召回率和保持可审计性的方案。

以上均为未来规划，不能描述成当前已经完成的功能。

## 8. 简历项目描述示例

**FinRisk Agent Studio — Evidence-first 金融研究 Agent 工作台**

- 使用 FastAPI、Pydantic AI/Pydantic Graph 与 React 构建九步金融风险研究工作流，接入 SEC、XBRL、transcript、Web 与可选 Neo4j，并提供可审计 trace 和后台运行 API。
- 设计 evidence lineage、point-in-time snapshot、claim grounding、来源质量和 human-review gate，区分 `completed`、`needs_review`、`partial/unavailable` 与 `failed`，避免静默降级。
- 将 LLM 限定在 typed extraction、工具选择和证据解释，把评分、图边确认、权限、预算与安全检查保留为确定性逻辑；统一多 provider model factory 并移除重复 runtime。
- 实现供应链递归图与 Sankey、财务事实/restatement/TTM、同行比较、Scenario/Multiple/DCF 估值、Watchlist 监控和财报后复盘；支持 SQLite 迁移/备份和无密钥 static demo。

实际投递时应根据岗位删减到两三条，并把你能现场解释、能展示测试证据的内容放在最前面。
