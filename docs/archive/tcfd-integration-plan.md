# FinRisk 与 TCFD 项目合并方案

状态：提案，尚未迁移运行时代码；最后更新：2026-09-03

领域配套文档由 `llm_tcfd` 研究仓库维护：

- `docs/migration/v2-evidence-first-plan.md`
- `docs/migration/step-by-step.md`
- `docs/migration/review-and-acceptance.md`

## 1. 结论

两个项目可以合并，但这里的“合并”应定义为：

> 以 **FinRisk Agent Studio** 为生产主仓库和统一产品，把气候披露评审实现为独立领域能力；
> `frequency_analyzer` / `llm_tcfd` 保留为研究、数据和历史基准仓库。

不应执行以下形式的机械合并：

- 不使用 `git merge --allow-unrelated-histories` 把两棵目录树直接叠在一起；
- 不把整个 `src/tcfd_extractor/` 原样复制到 FinRisk；
- 不让 FinRisk 在生产运行时通过 Git、相对路径或 editable install 依赖研究仓库；
- 不在两个仓库各实现一套 V2 证据模型、模型运行时和前端；
- 不把当前 A/B 关键词共现结果直接升级为 TCFD、IFRS S2 或 ESRS 合规结论。

最合适的迁移策略是“**单一生产实现 + 可追溯的选择性移植**”：V2 的新生产代码直接在
FinRisk 中实现；TCFD 仓库只提供经过审核的算法、词表、评估样例和历史对照，不再先在旧仓库
完成整套 V2 后二次搬运。

## 2. 本次判断依据与基线

本方案基于两个本地仓库的实际代码，而不只依据产品设想。

| 仓库 | 本次检查基线 | 当前事实 |
|---|---|---|
| `FinRisk-Agent-Studio` | `145e34b2e3a39cf78f78a226f20108c97d30962d`，工作树干净 | 已有 SEC/XBRL、通用证据候选、Pydantic AI runtime、workflow、质量门禁、图推理、人工复核 API、React 工作台 |
| `llm_tcfd` / `frequency_analyzer` | `4ef1c0f49853d2821dbf1ead73259d65475ca8d3`，工作树干净 | 当前生产代码仍是关键词提取、共现、语义相关性过滤、词表审核、聚类和历史报告；V2 证据模型目前是文档提案，不是已经实现的代码 |

开始任何跨仓库移植前，必须先分别形成可复现基线。上表记录的是本方案写入 FinRisk 时的两个
基线；实际移植若发生在后续 commit，provenance manifest 必须改为对应的完整 source SHA，不能
只引用分支名或较早基线。

### 2.1 FinRisk 已有的可承接能力

- `src/schemas/evidence.py` 已定义通用 `Evidence`，包含来源、quote、字符跨度和时间信息；
- `src/evidence/candidates.py` 已把工具 trace 规范化为 `EvidenceCandidate`，并记录来源质量、
  grounding、接受/拒绝/待复核状态；
- `src/ai/` 已提供模型工厂、Pydantic AI adapter、typed client、usage、消息记录与 tool trace；
- `src/data/` 已提供 SEC filing、section、CIK/ticker、XBRL 和 entity resolution；
- `src/evaluation/` 与 `src/workflows/quality_gate.py` 已提供可扩展的质量门禁框架；
- `src/graph_reasoning/` 已限制模型解释经过绑定和验证的图路径；
- `src/agents/state.py` 与 `src/api/agent_runs.py` 已有候选证据和人工复核状态/API；
- `frontend/` 已有 run timeline、证据候选、claim/evidence、evaluation 和 review 交互。

### 2.2 TCFD 仓库已有的可提供能力

- `SmartChunker` 支持中文/英文标题、段落、句子和硬上限的无损切分；
- `frequency/cooccurrence.py` 提供确定性的 A/B 词表召回和上下文定位；
- `docs/word-bags/` 保留原始、合并、LLM 校验和辅助风险词表；
- `domain/keywords.py`、`domain/evaluation.py` 提供严格 Pydantic 输出和跨字段约束的样例；
- `workflows/_concurrency.py` 与失败模型体现有界并发、逐项失败和部分成功语义；
- `evals/` 已有小型 synthetic 回归集、失败单列和版本化 live eval runner；
- A 股年报抽样、文件名解析、中文年报经验和历史输出可作为数据接入与回归研究依据。

### 2.3 不能忽略的现状差距

FinRisk 的现有证据合同并不等于 V2 气候证据合同：

- `EvidenceCandidate.quote` 可为空，且候选可能仅依据来源质量与 lexical grounding 自动进入
  `accepted`；这不满足披露结论的逐字引用要求；
- `Evidence` 只有可选字符跨度，没有 document hash、page、block、bbox/cell、标准版本和
  requirement mapping；
- `NormalizedEvidence` 是风险报告的扁平展示模型，不足以承担不可变、可复核的证据事实；
- `FinRiskWorkflowState` 已同时承载多代风险工作流字段，继续加入完整气候评审状态会扩大耦合；
- `RiskType="climate"` 只能表达风险分类，不能表达治理、战略、风险管理、指标与目标等披露要求；
- 现有风险分数和风险报告不能替代五状态的 requirement assessment，也不能作为合规总分。

反过来，TCFD 仓库也没有可直接迁移的完整 V2 实现：当前 `SourceChunk` 只有 `source_id`、顺序和
文本；`CooccurrenceContext` 只有词对、passage 和位置；当前 Agent 输出是关键词、相关性或词表
决定，而不是 `ClimateEvidence`、`VerificationDecision`、`MetricObservation` 和
`RequirementAssessment`。

## 3. 合并后的产品与仓库职责

### 3.1 产品边界

FinRisk 对外保持一个产品，提供两个相互连接但不混淆的分析域：

1. **Financial / Risk Intelligence**：现有 filing 风险、财务事实、同行、估值、供应链与图推理；
2. **Climate Disclosure Intelligence**：TCFD/IFRS S2/ESRS E1 requirement 评审、气候证据、
   指标与财务影响连接。

气候页面可以引用已有财务事实和图节点，但“披露是否充分”与“财务风险有多大”必须是两个结果，
不能共用一个分数或状态字段。

### 3.2 源码所有权

| 能力 | 唯一生产所有者 | TCFD 仓库后续角色 |
|---|---|---|
| LLM/provider/runtime、tool trace、usage | FinRisk `src/ai/` | 不再独立演进生产 runtime |
| SEC、XBRL、Web、entity resolution | FinRisk `src/data/`、`src/tools/` | 仅保留研究所需输入适配 |
| 通用 source/document locator | FinRisk `src/evidence/` | 提供中文年报定位测试与经验 |
| 标准 registry 与映射 | FinRisk `src/disclosures/` | 保存研究草案，不作为生产 source of truth |
| 气候模型、指标与 assessment | FinRisk `src/domains/climate/` | 提供算法原型与对照基线 |
| 气候 Agent 与检索实现 | FinRisk `src/ai/agents/climate/`、`src/retrieval/climate/` | 提供 prompt、召回算法与对照基线 |
| 生产 workflow、API、存储、前端 | FinRisk | 无第二套生产入口和 UI |
| 词表研究、共现实验、聚类、t-SNE | TCFD 仓库 | 继续作为研究能力维护 |
| gold/benchmark 原始标注 | 建议先由 TCFD 仓库管理，发布冻结版本到 FinRisk 测试资产 | 负责标注历史与研究说明 |

### 3.3 依赖方向

允许的依赖方向是：

```text
TCFD research artifact
  --审核、固定版本、记录 hash/provenance-->
FinRisk climate domain
  --> shared AI / evidence / data / evaluation / graph / API / frontend
```

FinRisk 不能反向 import `tcfd_extractor`。两个 Git 仓库之间也不能形成运行时循环依赖。研究算法
进入生产后，生产版本由 FinRisk 维护；若研究仓库继续改进算法，应通过新的移植评审进入，而不是
运行时自动跟随。

## 4. 目标数据合同

### 4.1 四层证据模型

应保留 FinRisk 的通用候选，但不能让它承担所有含义：

```text
ToolExecutionEvent / DocumentBlock
        │
        ▼
EvidenceCandidate              通用召回结果，允许待验证
        │ deterministic locator checks + semantic verification
        ▼
ClimateEvidence                规范化、不可变、逐字可定位的气候证据
        │ many-to-many mapping
        ▼
RequirementEvidenceMapping     对某一标准要求的支持/部分支持/反证关系
        │ deterministic rubric aggregation
        ▼
RequirementAssessment          present / partial / not_found /
                               uncertain / not_applicable
```

关键规则：

- `EvidenceCandidate.status="accepted"` 只表示通用候选已被运行时接受，不能直接推出 requirement
  为 `present`；
- `ClimateEvidence` 必须包含 `document_id`、`document_hash`、`block_id`、精确 quote/span、
  locator、evidence type、抽取/验证 revision；
- 标准映射必须独立建模。一条气候证据可同时映射 TCFD、IFRS S2 和 ESRS E1，不能复制三份原文；
- mapping 必须记录 `exact`、`broader`、`narrower` 或 `related` 以及方向、理由和 registry version；
- `RequirementAssessment` 只能由确定性 rubric 聚合已验证证据得出；模型不能直接填写最终状态；
- 数值进入 `MetricObservation`，保留 raw value、单位、期间、Scope/boundary、表头/脚注 locator 和
  normalization trace。

### 4.2 对 FinRisk 现有合同的处理

| 现有合同 | 处理方式 |
|---|---|
| `src.evidence.candidates.EvidenceCandidate` | 保留为通用候选；增加可选 `document_locator`、producer/revision 或通过关联表补充，不添加气候专属字段 |
| `src.schemas.evidence.Evidence` | 保持通用 claim provenance；抽取共享 `SourceLocator`/`DocumentRef`，避免与 `ClimateEvidence` 互相复制但语义不同 |
| `NormalizedEvidence` | 继续服务现有 FinRisk 风险报告；不得作为气候评审 canonical store |
| `Claim` | 可用于气候到财务影响的研究断言；requirement 状态本身不是 `Claim` |
| `HumanReviewItem` | 扩展 object type，支持 climate evidence、mapping、metric 和 assessment conflict |
| `FinRiskWorkflowState` | 保持现有流程兼容；新增独立 `ClimateDisclosureWorkflowState`，共享 runner/trace 机制，不继承大状态对象 |

## 5. 代码复用分类

### 5.1 FinRisk：可以直接复用或小幅扩展

| 模块 | 复用判断 | 必要扩展 |
|---|---|---|
| `src/ai/model_factory.py`、runtime adapter、message recorder、usage | 直接复用 | 注册 climate typed agents、prompt/agent revision 和预算 profile |
| `src/schemas/tool_trace.py` | 直接复用 | stage/item/document/requirement correlation ID |
| `src/data/sec_client.py`、`filing_fetcher.py`、`sec_sections.py` | 美国申报接入直接复用 | 不只读取 Item 1A；需覆盖治理、MD&A、可持续相关段落及附件 |
| `src/data/xbrl.py` 与财务事实层 | 直接复用 | 通过明确的 metric/impact mapping 连接气候指标，不把 XBRL 缺失当披露缺失 |
| `src/tools/search_router.py`、web fetch/browser 安全层 | 条件复用 | Web 证据与年报内披露必须标明不同 source scope，默认不能替代发行人披露 |
| `src/evaluation/engine.py`、validator 协议 | 直接复用框架 | 新增 locator、requirement、metric、completeness、status 语义 validator |
| `src/graph_reasoning/` | 条件复用 | 只让 verified evidence 绑定边；气候关系类型与财务影响路径需显式 schema |
| run store、auth、rate limit、redaction | 直接复用 | climate artifact retention、原文权限和下载脱敏策略 |
| React shell、timeline、candidate/review/evaluation 组件 | 复用交互模式 | 新建 Climate 页面和 requirement matrix；不能只换标题复用 risk score 卡片 |

### 5.2 TCFD：可以移植，但必须通过适配器或重构

| 来源 | 可复用部分 | 进入 FinRisk 前必须改变 |
|---|---|---|
| `SmartChunker` | 中文/英文结构边界、无损切分、硬上限算法和测试 | 输入/输出改为 `DocumentBlock`；保留页、标题路径、表格和 source span；不能只返回字符串 |
| `frequency/cooccurrence.py` | A/B 词表的高精度 lexical 召回思路 | 改为 `ClimateLexicalRetriever`；返回候选和命中 provenance；扫描所有有效命中、处理重叠/空词/归一化；不能决定证据成立 |
| `docs/word-bags/` | 中文领域词、同义扩展和风险邻接词 | 审核来源、许可证、维度语义、重复和版本；生成机器可读 manifest/hash；从“生产真值”降为 retrieval resource |
| keyword/relevance/lexicon Agent | prompt 约束、typed output、困难负例 | 重写输出为 candidate evidence/mapping/verifier；不得沿用 policy/market/technology/reputation 作为 TCFD 四支柱 |
| `_concurrency.py` 与失败测试 | 有界并发、输入输出守恒、失败单列 | 使用 FinRisk runner、budget、trace 和统一 failure code，不复制第二套执行框架 |
| `evals/` | 数据格式、manifest、失败不计为空预测的原则 | 扩充为 requirement + span + verification + assessment gold；人工复核；按公司/年份切分防泄漏 |
| sampler/parser | A 股 TXT 数据发现与回归抽样 | 提供 seed、manifest、hash、编码/年份/公司元数据；文件名只作为输入提示，不作为 canonical identity |

这里的“移植”是依据源代码重新实现并保留 provenance，不是把整个模块复制后长期并行维护。

### 5.3 必须重构，不能直接复用

1. **证据模型**：`MatchContext`、`SourceChunk`、`NormalizedEvidence` 都不能直接作为
   `ClimateEvidence`；缺少文档指纹、页/块/表格定位、标准版本和验证链。
2. **标准语义**：当前 policy/market/technology/reputation 是转型风险研究维度，不是 TCFD 的
   Governance/Strategy/Risk Management/Metrics & Targets 四支柱。
3. **候选成立逻辑**：固定 ±30 字或单句共现只能贡献一个 lexical channel；不得是全局 gate。
4. **文档摄取**：FinRisk 当前偏 SEC HTML/Item 1A，TCFD 当前偏预清洗 TXT；完整披露评审需要
   PDF/HTML/TXT 的统一 block/locator、OCR issue、表格和跨页处理。
5. **Agent 输出**：关键词和 binary relevance 必须升级为 span-grounded evidence、逐 requirement
   verifier 和 metric observation；模型失败不能伪装为 irrelevant 或 not found。
6. **工作流状态**：不向现有 `FinRiskWorkflowState` 继续堆字段；建立独立、版本化、可 checkpoint
   的 climate state 和 artifact contracts。
7. **报告**：现有 risk report、单一 final score 和旧 standalone HTML 都不能表达五状态、输入
   完整性、标准版本、冲突证据和 analysis completion。
8. **评估**：20 条 synthetic keyword/relevance case 只能做回归种子，不能作为发布阈值或披露
   质量证明。

### 5.4 不进入生产主仓库，继续研究或归档

- K-Means、t-SNE、聚类命名、年度词频图和历史统计报告；
- Markdown 共现文件作为模块间正式数据合同的做法；
- A 股目录布局、随机文件名采样和本地绝对路径假设；
- 已归档的年报截断 cleaner、CSV 合并脚本和旧 SDK 维护脚本；
- 旧 CLI 的 `extract`、`evaluate`、`review-lexicon`、`label-clusters` 实现；
- 单独的 TCFD 产品前端和第二套 API。

这些内容可继续在研究仓库复现实验。只有证明对新 retrieval/evaluation 有贡献的产物，才以固定
版本进入 FinRisk。

## 6. FinRisk 目标目录

以下布局遵守 FinRisk 当前以 `src.*` 为导入根的约定，同时避免继续膨胀现有风险 workflow：

```text
src/
├── evidence/
│   ├── candidates.py               # 现有通用候选
│   └── locators.py                 # shared DocumentRef / SourceLocator
├── disclosures/
│   ├── contracts.py                # Requirement / Mapping / profile contracts
│   └── registry.py                 # 版本化 registry loader + validation
├── data/disclosures/
│   ├── contracts.py                # SourceDocument / DocumentBlock / ingestion issue
│   ├── sec_adapter.py              # 复用现有 SEC 获取能力
│   ├── ashare_adapter.py           # 中文年报数据集适配，不进入通用 SEC 代码
│   ├── text_parser.py
│   └── pdf_parser.py
├── domains/climate/
│   ├── models.py                   # ClimateEvidence / MetricObservation 等
│   ├── taxonomy.py
│   ├── metrics.py                  # 确定性数值解析与归一化
│   ├── assessment.py               # 确定性 rubric 聚合
│   └── financial_impacts.py
├── retrieval/climate/
│   ├── lexical.py
│   ├── semantic.py
│   └── fusion.py
├── ai/agents/climate/
│   ├── evidence_extractor.py
│   └── verifier.py
├── reports/
│   └── climate.py
├── workflows/
│   └── climate_disclosure.py
└── api/
    └── climate_disclosures.py

frontend/src/
├── features/climate-disclosure/
└── ...existing shared timeline/evidence/review components

config/
├── disclosures/frameworks/              # 已审核、不可变的标准版本
│   ├── tcfd/<edition>/
│   ├── ifrs_s2/<edition>/
│   └── esrs_e1/<edition>/
└── climate/lexicons/<version>/           # 已审核的词表与 manifest
```

目录是目标边界，不要求一次创建全部空文件。每个阶段只创建当期有实现和测试的模块。

## 7. 分阶段迁移与审核门禁

本节的 `M0–M9` 是跨仓库合并门；领域正确性仍需同时通过既有 V2 审核手册的 `G0–G12`。

### M0：冻结基线、许可与 provenance

**改动位置**：两个仓库的文档和元数据，不移动生产代码。

**任务**：

- 固定上表两个基线，并在实际移植时记录精确 source/destination commit；
- 确认代码与词袋的授权。TCFD README 声称 MIT，但仓库没有 tracked `LICENSE`；FinRisk README
  目前只说明 Yahoo Finance 数据为 ODC-BY，没有给出项目代码许可证；在复制代码/数据前必须补齐；
- 建立 `docs/migration/tcfd-provenance.yaml`，逐项记录 source repo、commit、path、license、hash、
  destination、reviewer 和 semantic changes；
- 建立真实年报数据 inventory，区分可本地测试、可提交 fixture、可发送外部模型的数据；
- 冻结两个仓库的测试命令、fixture 和性能基线。

**出口 M0 / G0**：来源和许可明确；工作树与 commit 对得上；无真实年报或敏感原文误入 Git；
回滚只需删除尚未使用的 provenance 草案。

### M1：共享 locator 与气候领域合同

**改动位置**：FinRisk `src/evidence/locators.py`、`src/data/disclosures/contracts.py`、
`src/disclosures/contracts.py`、`src/domains/climate/models.py`。

**任务**：

- 定义版本化 `SourceDocument`、`DocumentBlock`、`SourceLocator`；
- 定义 `Requirement`、`ClimateEvidence`、`RequirementEvidenceMapping`、
  `VerificationDecision`、`MetricObservation`、`RequirementAssessment`、`DisclosureProfile`；
- 规定稳定 ID、hash、不可变字段、跨引用约束和 unknown major version 拒绝策略；
- 定义独立 `ClimateDisclosureWorkflowState` 与 manifest/checkpoint，不复用大状态对象；
- 只定义合同和纯校验，不接真实模型。

**出口 M1 / G2**：schema round-trip、immutability、span/hash、无悬空 ID、状态跨字段约束和
版本拒绝测试全部通过；现有 FinRisk API schema 无 breaking change。

### M2：统一文档摄取与市场适配

**改动位置**：FinRisk `src/data/disclosures/`。

**任务**：

- SEC adapter 复用现有 client/fetcher，但输出统一 blocks，而不是只抽 Item 1A；
- A-share adapter 移植数据发现知识，显式解析公司、代码、报告期、语言和 source hash；
- 实现 TXT/HTML 基线，随后接 PDF/OCR/table；所有清洗保留回源映射；
- 将 `SmartChunker` 的边界算法改造成 block-aware split，并移植其无损测试；
- ingestion issue 必须影响 run completeness，不能被吞掉。

**出口 M2 / G3**：中英文、空页、乱码、标题、长句、表格、跨页和失败 fixture 可对账；任意
quote 能回到源 block；删除新 adapter 即可回滚，不影响现有 filing workflow。

### M3：标准 registry 与跨框架映射

**改动位置**：FinRisk `src/disclosures/` loader 与
`config/disclosures/frameworks/` 版本化数据。

**任务**：

- 先实现经过审核的 TCFD 11 项兼容 profile；长期主 profile 为 IFRS S2；
- registry 固定 edition、来源、locator、hash、适用性、rubric、正/partial/反例；
- 将 retrieval hints 与 requirement 正文分开；
- 定义 TCFD ↔ IFRS S2 ↔ ESRS E1 有方向和关系类型的映射；
- draft 或未审核 registry 不能通过生产 profile loader。

**出口 M3 / G4**：Standards Reviewer 逐项签字；11 项完整、ID 唯一；版本更新不原地改写历史；
TCFD 结果不会冒充完整 IFRS S2/ESRS 评审。

### M4：移植 lexical retrieval 并构建混合召回

**改动位置**：FinRisk `src/retrieval/climate/` 和
`config/climate/lexicons/` 版本化 resources。

**任务**：

- 以 TCFD 共现算法为来源实现 `ClimateLexicalRetriever`；
- 词袋经许可、来源、去重和语义审核后以版本化 artifact 导入；
- 同时接标题/section、BM25/全文、semantic 等通道；
- fusion 保留每个通道的 raw score、rank、hit span、resource revision 和失败；
- 按 requirement 配额取候选；无候选只表示 retrieval 结果为空，不生成 `not_found`。

**出口 M4 / G5**：在冻结 retrieval gold 上报告 Recall@k/MRR、通道贡献、最差切片、成本和失败；
A/B 通道可由 feature flag 单独关闭且不破坏工作流。

### M5：气候证据抽取、验证与数值解析

**改动位置**：FinRisk `src/ai/agents/climate/`、`src/domains/climate/models.py`、
`src/domains/climate/metrics.py` 和 climate validators。

**任务**：

- 使用 FinRisk 统一 Pydantic AI runtime，创建逐候选 typed extractor；
- 先做 quote/span/hash 的确定性校验，再做逐 requirement 语义 verifier；
- unsupported、conflict、provider failure 和 parse failure 分开记录；
- 数值抄录采用确定性 parser + typed observation，模型只辅助识别语义，不成为数值唯一来源；
- 记录 model/provider、prompt、agent、registry、usage、latency、retry 和 endpoint；
- 复用 human review 基础设施处理低置信、冲突、表格和适用性问题。

**出口 M5 / G6–G7**：所有进入肯定性聚合的 quote 100% 可回源；模型/解析失败不变成否定；
metric 倍率、负号、单位、期间、Scope、表头和脚注测试通过。

### M6：确定性 assessment、报告和 artifact store

**改动位置**：FinRisk `src/domains/climate/assessment.py`、`src/reports/climate.py`、run store 和 renderer。

**任务**：

- 固定 `applicability → completeness → present → partial → not_found` 的聚合顺序；
- 关键阶段失败、截断、未决冲突产生 `uncertain`；
- 生成 requirement matrix、证据引用、指标表、输入质量、limitations 和 failure summary；
- MVP 不生成企业单一总分、合规徽章或跨公司排名；
- summary 只能引用 profile 中的确定性计数，不让 LLM 重算；
- artifacts 原子写入并含 schema/registry/input/code/prompt/model hash。

**出口 M6 / G8–G9**：五状态 fixture 可独立重算；`present/partial` 全部有 verified evidence；
report 数字与 profile 完全一致；新 workflow/artifact root 可整体关闭回滚。

### M7：连接财务事实、图推理和供应链

**改动位置**：FinRisk `src/domains/climate/financial_impacts.py`、graph contracts 和 research 层。

**任务**：

- 将碳价、能源、合规成本、停产、减值、保险等气候事实映射为候选财务影响；
- 只用 verified evidence ID 绑定 graph edge；模型只能解释已有路径；
- 区分 issuer disclosure、外部市场证据、财务事实和推断；
- 允许供应链节点复用，但关系类型、时间范围、方向和 counter-evidence 必须显式；
- 气候披露状态不能因存在外部新闻或图路径而自动升级。

**出口 M7**：每条图边和财务影响可回到证据；删除 climate projection 不会删除现有 FinRisk 图数据；
无 LLM-only confirmed edge。

### M8：API、前端和人工审核闭环

**改动位置**：FinRisk `src/api/climate_disclosures.py` 与
`frontend/src/features/climate-disclosure/`。

**任务**：

- 新建 `/climate-disclosures` run/report/evidence/assessment/review endpoints；
- 复用 auth、rate limit、store、timeline 和 review action 模式；
- 增加 requirement matrix、原文 locator、标准版本、conflict、metrics 和 completeness 展示；
- review 决定必须记录 reviewer、时间、理由、旧值/新值，且触发可重算 assessment；
- 不复用 risk score 卡片来假装 disclosure score。

**出口 M8**：API contract、权限、并发、resume、review replay 和前端桌面/移动/无障碍测试通过；
feature flag 默认关闭，现有 FinRisk 页面无回归。

### M9：shadow、切换与研究仓库收口

**改动位置**：两个仓库的发布、文档和 CI。

**任务**：

- 在固定中英文年报集上并行运行旧共现链路与新 climate workflow；
- 比较召回贡献、证据精度、requirement 状态、失败、abstention、成本和耗时，不比较不可等价的
  单一“分数”；
- 由 Engineering、Standards、Data、Evaluation、Release 共同审核差异；
- 先启用 beta，再切默认入口；演练关闭 feature flag 和恢复旧版本 artifact reader；
- TCFD README 标注其 research predecessor 身份，冻结旧生产声明；
- 旧流程只有在历史复现需求、数据导出和用户迁移完成后才归档，不立即删除。

**出口 M9 / G10–G11**：无 P0/P1；所有机械硬门通过；shadow 阈值有真实基线和批准记录；回滚
演练成功；FinRisk 成为唯一生产 source of truth。

## 8. Git 与提交策略

### 8.1 分支

- TCFD：迁移设计、清理归档和教程校正已分批提交；后续研究改动继续保持独立提交；
- FinRisk：从预定集成基线创建 `feature/climate-disclosure`；
- 每个 `M` 阶段使用独立 PR/提交组；未通过 gate 不合入下一阶段的生产默认路径；
- 不在 TCFD dirty worktree 中生成补丁后直接覆盖 FinRisk 同名文件。

### 8.2 推荐提交组

1. `docs(climate): record integration baseline and provenance`
2. `feat(evidence): add document locator contracts`
3. `feat(climate): add versioned domain contracts`
4. `feat(disclosures): add ingestion adapters`
5. `feat(disclosures): add reviewed requirement registry`
6. `feat(climate-retrieval): port lexical channel with provenance`
7. `feat(climate): add evidence extraction and verification`
8. `feat(climate): add deterministic assessment and report`
9. `feat(climate-graph): connect verified impacts`
10. `feat(api): expose climate disclosure workflow`
11. `feat(frontend): add climate disclosure workspace`
12. `test(climate): add shadow and release evidence`
13. `docs(tcfd): mark research predecessor and cutover policy`

合同、registry、算法、UI 和数据不应塞进一个大提交。每个提交都应能说明来源、语义变化和对应测试。

### 8.3 源码历史与 attribution

选择性重写会失去跨仓库的 `git log --follow`，因此必须用 provenance manifest 补足。对于实质复制的
文件，提交信息应写明：

```text
Source-Repository: git@github.com:somAzzz/llm_tcfd.git
Source-Commit: <full sha>
Source-Path: <path>
Port-Changes: <contract/algorithm/semantic changes>
```

如果某个独立文件确实需要保留逐提交历史，可对该文件筛选 patch 后再重构；不要为少数文件引入
完整 unrelated history 或 subtree。

## 9. 测试与发布证据

### 9.1 每阶段最低测试

- 两个仓库各自原有默认测试不回归；
- FinRisk schema/API/frontend contract tests；
- 中英文 document/locator property tests；
- registry 内容、版本和 mapping consistency tests；
- lexical retriever 与旧实现的冻结 fixture parity test，以及针对旧实现缺陷的新行为测试；
- extractor span、verifier、metric、assessment 的分层单元和 eval；
- provider timeout、坏 JSON、OCR/table failure、budget exhaustion、resume 和 rollback tests；
- prompt injection、路径遍历、日志/trace 原文泄漏和外部 provider 数据策略测试；
- graph edge 必须引用 verified evidence 的 architecture test。

### 9.2 跨仓库 shadow 数据集

至少包含：

- SEC 10-K/20-F 的不同年份与行业；
- A 股中文 TXT/PDF、OCR 噪声和表格密集报告；
- TCFD 明确披露、部分披露、无候选、输入不完整和不适用样例；
- 关键词困难负例，如普通 IT“技术”、普通产品“市场”和公司名称误命中；
- 同一证据映射多个框架、冲突证据、单位不明和跨页表头；
- 模型不可用、检索通道失败和人工复核未完成。

真实年报不默认进入 Git。提交的 fixture 应为授权、最小化、脱敏或合成内容，并在 manifest 记录来源
策略。数据切分按公司/年份分组，冻结 test 不得用于 prompt、query、fusion 或阈值调参。

### 9.3 发布硬门

除领域阈值外，以下机械门必须为 100%：

1. 发布 artifact 全部通过其声明 schema；
2. 所有 `present/partial` 可追到 verified quote/span；
3. quote 与源 block/hash 一致；
4. run 中每个 item 可守恒为成功或结构化失败；
5. manifest 可唯一确定输入、代码、registry、模型、prompt 和配置；
6. 任一关键阶段失败不会被展示成 `not_found`；
7. feature flag 回滚不会破坏现有 FinRisk workflow 和数据。

## 10. 主要风险与控制

| 风险 | 后果 | 控制 |
|---|---|---|
| 直接复用 `accepted` candidate | 未验证内容进入肯定披露结论 | 强制 ClimateEvidence + mapping + verifier 三层门 |
| 把 climate risk 当 disclosure requirement | 只找到风险语句，遗漏治理/指标等要求 | 独立 requirement registry 和 state/report |
| 继续膨胀 `FinRiskWorkflowState` | 版本字段混杂、API 与存储耦合 | 独立 climate state，共享基础设施而非继承业务状态 |
| SEC Item 1A 偏置 | 美国风险段有效，但披露覆盖严重不足 | 全文/多 section ingestion，按 requirement 检索 |
| A 股文件名成为主键 | 重命名或格式变化造成身份漂移 | source hash + 显式 metadata + resolver |
| 词袋来源/许可不清 | 数据无法合法、可审计地迁移 | M0 license/provenance gate；未通过只保留在研究仓库 |
| 两套 Pydantic AI runtime | 配置、trace、成本和失败语义分叉 | FinRisk 是唯一生产 runtime |
| 图推理放大模型猜测 | 无证据的气候财务路径被当事实 | verified evidence binding + edge validator + inference 标签 |
| 漂亮 UI 隐藏 incomplete run | 用户把缺失分析当未披露 | 同屏展示 completeness、uncertain、failure 和标准版本 |
| 一次性大迁移 | 难审、难回滚、难定位质量变化 | M0–M9 小步 PR、feature flag、shadow 和逐门审核 |

## 11. 开始实施前必须确认的事项

以下事项不能靠代码默认值替代产品或治理决定：

1. FinRisk 项目代码的正式许可证，以及 TCFD 代码/词袋的授权和 attribution；
2. 首个生产 profile 是“TCFD 11 项兼容评审”还是直接以 IFRS S2 子集命名；本方案建议前者；
3. 首批市场范围：建议同时保留 SEC adapter 和 A-share adapter，但先用一个市场完成端到端门禁；
4. 真实年报能否发送给外部模型、允许的 endpoint/地域、日志保留期；
5. gold 的审核者、冻结策略和发布阈值 owner；
6. beta 启用范围、旧 CLI 支持期限和最终研究仓库维护状态。

这些决定应形成 ADR 或审核记录。未决定时可以完成纯合同、fixture 和本地离线路径，但不能对外宣布
生产切换或标准覆盖。

## 12. 合并完成定义

只有同时满足以下条件，才可以称两个项目已完成合并：

- FinRisk 中存在独立、版本化、可回滚的 climate disclosure workflow；
- 生产运行不依赖 TCFD 仓库路径、环境或 Git 可用性；
- 被移植的每项代码/数据都有 source commit、hash、许可和语义变更记录；
- 所有肯定披露结论都有 verified source locator，所有关键失败都传播为 incomplete/uncertain；
- TCFD、IFRS S2、ESRS E1 的要求与映射有固定版本，不把兼容评审冒充全面合规审计；
- 财务、图和供应链连接只消费已验证证据，并区分事实与推断；
- API、前端、人工复核、评估、数据治理和回滚全部通过对应 gate；
- 旧 TCFD 仓库已明确转为研究/benchmark predecessor，且没有仍在使用却被误删的历史复现能力；
- 现有 FinRisk financial/risk workflow 和研究功能无回归。

在这些条件之前，更准确的表述是“正在把 TCFD 研究能力迁入 FinRisk”，而不是“两个系统已经合并”。
