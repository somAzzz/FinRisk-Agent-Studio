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

工具通过 catalog 注册，并带有 scope、risk、evidence kind、参数 schema 和结果上限。不同 Agent 只能看到当前任务允许的工具；交互或写操作还需要执行时再次检查，不能只靠 prompt 约束。

每次运行记录：

- planner/subgoal 和状态转换；
- tool name、参数摘要、结果 envelope、耗时和错误；
- provider/model、token usage 和 fallback；
- evidence candidate 的接受/拒绝；
- human review 与 deferred approval；
- run ID、conversation ID 和 parent run 关联。

消息以版本化 append-only batch 保存。resume 从服务端恢复历史并创建新的 run ID，operation ID 和事务防止重复追加或重复领取审批任务。

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

critical step 的 blocker 会使工作流失败；非关键的市场或图步骤出问题时，系统可以继续生成有限结果，但终态进入 `needs_review`。这使“技术执行失败”和“研究完成但需要判断”成为不同状态。

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

## 4. 面试时怎么介绍

### 4.1 30 秒版本

> 我做了一个 evidence-first 的金融研究 Agent 工作台。它会从 SEC 文件、财务事实、电话会和网页中提取风险证据，经过九步 Pydantic Graph 工作流完成归一化、确定性评分、图推理、报告和质量门禁。和普通 RAG demo 不同，我重点解决了证据 lineage、point-in-time、失败降级和人工复核：每个结论能回源，模型不能直接创建确认图边或给买卖建议，证据不足会进入 needs-review。后面我又把结果接成了快照、预期、估值、Watchlist 和财报复盘闭环，并做了 FastAPI、React、SQLite/Neo4j 以及可离线演示的完整产品形态。

### 4.2 两分钟版本

可以按“问题—方案—难点—结果”讲：

> 金融研究 Agent 的难点不是生成一篇报告，而是如何证明报告中的事实来自哪里、在什么时间已知，以及外部服务失败时系统有没有误导用户。为此我把系统设计成 evidence-first workflow，而不是聊天机器人。
>
> 后端用 FastAPI，核心研究链路用 Pydantic Graph 编排九个步骤，公共状态全部用 Pydantic model。Pydantic AI 负责 typed output 和受限工具调用，规则代码负责 evidence confirmation、风险评分、图路径验证、权限、预算和质量门禁。所有运行都有 trace、usage、fallback 和 human-review 状态。
>
> 我重点做了三个工程难点。第一是异构证据归一化：SEC、XBRL、transcript 和网页的时间、来源与引用方式不同，我统一成稳定 evidence contract，并保留 lineage。第二是 point-in-time：快照和预期不能被后来数据回写，所以我实现了不可变快照、restatement 语义和变化检测。第三是失败语义：模型或 provider 不可用时可以降级，但必须显式标记 partial/unavailable/needs-review，不能把缺失当成否定结论。
>
> 产品上除了风险报告，还有供应链 Sankey、同行分析、情景和 DCF 估值、Watchlist 监控以及财报后复盘。前端是 React 工作台，存储默认 SQLite、图后端可选 Neo4j，demo/CI 不依赖外部密钥。这个项目让我真正处理了 Agent 系统的可审计性、可靠性和产品化，而不只是 prompt engineering。

### 4.3 深挖时推荐讲的三个故事

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

### 4.4 常见追问与回答要点

**为什么不用纯 RAG？**  RAG 解决召回和上下文问题，但不能自动解决证据生命周期、时间边界、权限、业务状态和发布门禁。FinRisk 把 RAG/搜索作为证据采集的一环，而不是整个系统。

**怎么降低幻觉？**  typed output 只解决结构，不保证事实正确；因此还需要 source/quote 校验、evidence ID、claim grounding、图路径验证、来源质量、确定性报告规则和 human review。

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

推荐只打开少量关键文件：

1. `src/workflows/finrisk_workflow.py`：步骤和 critical policy；
2. `src/ai/graphs/finrisk.py`：Graph 如何复用公共 state；
3. `src/schemas/finrisk.py`：typed contract；
4. `src/evaluation/engine.py`：质量门禁如何汇总；
5. `src/graph_reasoning/subsystem.py`：受控图推理；
6. `src/research/orchestrator.py`：工作流结果如何进入 point-in-time snapshot；
7. `src/api/workflows.py`：异步 run ID 与查询接口。

不要逐目录念技术栈。面试官更关心的是你为何这样划分边界、失败时发生什么、如何证明它可靠。

## 6. 不要过度声称

- 当前是 `v0.1` release candidate；仓库没有产品 Git tag，不能说已正式发布 `v0.1.0`。
- GitHub Pages 是 static fixture dashboard，不是在线实时研究服务。
- 外部 SEC、transcript、search、LLM 和 Neo4j 的完整结果依赖网络、密钥或独立服务。
- 项目不是生产级多租户 SaaS，没有交易执行，也不输出买卖建议。
- Agent memory 已有模型和 guardrail 基础，但长期召回质量、过期和无人值守恢复仍在后续范围。
- 分部数据、外部 consensus、自动 FX 和通知 adapter 尚未成为默认完整能力。

准确说明边界不会削弱项目，反而能体现你理解“代码能跑”和“生产可靠”之间的差距。

## 7. 简历项目描述示例

**FinRisk Agent Studio — Evidence-first 金融研究 Agent 工作台**

- 使用 FastAPI、Pydantic AI/Pydantic Graph 与 React 构建九步金融风险研究工作流，接入 SEC、XBRL、transcript、Web 与可选 Neo4j，并提供可审计 trace 和后台运行 API。
- 设计 evidence lineage、point-in-time snapshot、claim grounding、来源质量和 human-review gate，区分 `completed`、`needs_review`、`partial/unavailable` 与 `failed`，避免静默降级。
- 将 LLM 限定在 typed extraction、工具选择和证据解释，把评分、图边确认、权限、预算与安全检查保留为确定性逻辑；统一多 provider model factory 并移除重复 runtime。
- 实现供应链递归图与 Sankey、财务事实/restatement/TTM、同行比较、Scenario/Multiple/DCF 估值、Watchlist 监控和财报后复盘；支持 SQLite 迁移/备份和无密钥 static demo。

实际投递时应根据岗位删减到两三条，并把你能现场解释、能展示测试证据的内容放在最前面。
