# 气候披露迁移总图：从 TCFD 研究管线到 FinRisk 领域能力

> 路线状态：未进入当前产品路线。本图只在
> [Chapter 10 重启门](10-integration-boundaries.md)通过后才变成可执行计划。

## 这张图解决什么问题

Chapter 6–9 的 [runtime 迁移总图](../runtime/MIGRATION_MAP.md)说明 FinRisk 如何从自定义 tool loop 切换到
Pydantic AI。本图说明另一个问题：如何把 `llm_tcfd` 的研究资产选择性迁入已经完成 runtime
重构的 FinRisk，而不复制第二套基础设施或沿用错误业务语义。

权威架构边界见 [TCFD 合并方案](../../../tcfd-integration-plan.md)。本图只负责把源资产、
目标文件、教程章节和审核门对应起来。

## 起点与终点

```text
llm_tcfd / frequency_analyzer
  keyword extraction
  A/B co-occurrence
  relevance filtering
  lexicon review
  clustering / historical report
             │
             │ reviewed selective port
             ▼
FinRisk Agent Studio
  shared document/evidence infrastructure
  versioned disclosure requirements
  hybrid retrieval
  typed climate evidence Agents
  deterministic verification/metrics/assessment
  API + review + frontend + eval
```

终点不是把左侧目录放到 `src/tcfd_extractor/` 子目录，而是让 FinRisk 拥有唯一生产实现；左侧继续
作为 research/benchmark predecessor。

## 仓库基线

| 仓库 | 教程参考 commit | 角色 |
| --- | --- | --- |
| FinRisk | `145e34b2e3a39cf78f78a226f20108c97d30962d` | Pydantic AI runtime 已完成的生产基线 |
| TCFD | `4ef1c0f49853d2821dbf1ead73259d65475ca8d3` | 研究算法、词表、eval 与历史实现来源 |

练习者使用其他 revision 时必须在 provenance manifest 记录自己的完整 SHA。

## 章节路线

| 章节 | 迁移问题 | 主要输出 | 合并门 |
| --- | --- | --- | --- |
| 10 | 谁拥有生产代码，来源是否合法可追踪？ | provenance、ADR、跨仓库边界测试 | M0/G0 |
| 11 | 什么才是文档、证据、映射和 assessment？ | 版本化纯领域合同、独立 state | M1/G2 |
| 12 | 如何让中英文报告内容精确回源？ | disclosure adapters、blocks、locators、issues | M2/G3 |
| 13 | 如何从标准要求召回候选？ | registry、mapping、hybrid retrieval | M3–M4/G4–G5 |
| 14 | 模型在哪两处发挥作用？ | typed extractor、verifier、metric parser | M5/G6–G7 |
| 15 | 如何形成可审计产品结果？ | deterministic assessment、report、API/UI/HITL | M6–M8/G8–G9 |
| 16 | 如何证明质量并安全切换？ | layered eval、shadow、release/rollback | M9/G10–G11 |

## 源资产到目标职责

| TCFD 来源 | 可保留的知识 | FinRisk 目标 | 处理方式 | 章节 |
| --- | --- | --- | --- | --- |
| `src/tcfd_extractor/chunker.py` | 中英文边界、软/硬上限、无损性质 | `src/data/disclosures/chunking.py` | 改写为 block-aware，保留 locator | 12 |
| `frequency/cooccurrence.py` | A/B lexical signal、窗口/句子思想 | `src/retrieval/climate/lexical.py` | 重构；只产生 CandidateHit | 13 |
| `docs/word-bags/` | 中文词汇与同义扩展 | `config/climate/lexicons/<version>/` | 许可/来源审核后发布版本化 artifact | 10、13 |
| `domain/keywords.py` | strict model、跨字段约束经验 | climate output/schema tests | 借鉴，不沿用四维业务语义 | 11、14 |
| `domain/evaluation.py` | success/failure 分离、统计约束 | climate eval models | 重写为 requirement/span/verdict gold | 16 |
| `ai/agents/keyword.py` | typed output、source-span 约束 | evidence extractor | 重写输出和 instruction | 14 |
| `ai/agents/relevance.py` | 困难负例和语义过滤经验 | requirement verifier | 改为逐 mapping verdict | 14 |
| `ai/agents/summary.py` | narrative 不重算统计的原则 | optional profile narrator | 最后才接，可不采用 | 15 |
| `workflows/_concurrency.py` | 有界并发、稳定顺序 | FinRisk workflow runner | 复用原则，使用现有 runtime/budget | 14 |
| `domain/failures.py` | 逐项失败与 partial result | FinRisk failure taxonomy | 映射语义，不复制第二套枚举 | 11、14 |
| `evals/` | 默认离线、live 显式、失败不当空预测 | `eval/climate_disclosure/` | 扩展标注单位和分层指标 | 16 |
| `sampler.py`、filename parser | A 股数据发现经验 | `ashare_adapter.py` | seed/manifest/hash；文件名只是 hint | 12 |
| clustering/t-SNE/visualization | 历史研究与展示 | 无生产目标 | 留在研究仓库 | — |
| Markdown co-occurrence parser | 历史产物复现 | shadow legacy adapter（临时） | 不作为新模块合同 | 16 |
| 旧 CLI | 研究复现入口 | 无生产复制 | 弃用窗口后归档 | 16 |

## FinRisk 目标依赖图

```text
src/data/disclosures
  -> src/evidence/locators
  -> DocumentBlock

src/disclosures
  -> Requirement / Registry / Framework Mapping

src/retrieval/climate
  -> DocumentBlock + Requirement
  -> EvidenceCandidate / CandidateHit

src/ai/agents/climate
  -> AgentDeps + Pydantic AI
  -> climate domain output models

src/domains/climate
  -> pure models + metrics + assessment
  X  pydantic_ai / FastAPI / concrete stores

src/workflows/climate_disclosure
  -> ingestion + registry + retrieval + Agents + assessment

src/api + frontend
  -> stable workflow/profile/review contracts
```

`domains/climate` 的 `X` 是禁止依赖。Agent 放在 `src/ai/agents/climate`，不是领域包内部；这保证
业务证据和状态在没有模型服务时仍能校验、重算和读取。

## 四层证据迁移

```text
旧 MatchContext / 新各通道命中
              │
              ▼
EvidenceCandidate / CandidateHit
  只代表值得检查
              │ locator + extractor
              ▼
ClimateEvidence
  原文、hash、位置不可变
              │ many-to-many mapping + verifier
              ▼
RequirementEvidenceMapping + VerificationDecision
  表达对特定要求的支持关系
              │ deterministic rubric
              ▼
RequirementAssessment
  present / partial / not_found / uncertain / not_applicable
```

旧 `relevant=True` 最多帮助构造候选或标注参考，不能直接映射成 `present`。

## 不可直接复用的同名概念

| 容易误用 | 为什么不同 | 正确处理 |
| --- | --- | --- |
| `EvidenceCandidate.accepted` | 运行时候选接受，不代表披露证据已验证 | 经过 locator、extractor、mapping、verifier |
| `NormalizedEvidence` | 风险报告展示模型，缺少完整定位/版本 | 保留现有用途，新建 ClimateEvidence |
| `RiskType="climate"` | 风险主题，不是披露要求 | 使用 registry requirement |
| policy/market/technology/reputation | 转型风险业务分类 | 不映射成 TCFD 四支柱 |
| relevance rate | 共现候选中的相关比例 | 不与披露 coverage 比较 |
| risk score | 研究优先级 | 不作为合规/披露分数 |

## 提交顺序

```text
ch10 provenance and repository boundary
  -> ch11 contracts and independent state
  -> ch12 traceable ingestion
  -> ch13 registry and retrieval
  -> ch14 typed extractor/verifier
  -> ch15 assessment and product integration
  -> ch16 eval, shadow and cutover
```

每章 DoD 通过后再提交。禁止把合同、词表、Agent、API、UI 和真实数据塞入一个大提交。

## 最终 source gate

完成 Chapter 16 后至少自动检查：

- FinRisk 不 import/依赖 TCFD 工作区；
- domain 不 import Pydantic AI、API 或具体 I/O；
- Agent 只输出 proposal/verdict，不写最终 assessment；
- `present/partial` 必须引用 verified source span；
- failure/uncertain/not_found 不互相降级；
- registry、model、prompt、input 和 code revision 可从 manifest 确定；
- 旧 A/B 算法只在 retrieval channel 或 shadow legacy adapter 中出现；
- feature flag 关闭时现有 FinRisk workflow 无回归；
- 未授权真实报告不进入 Git、外部 provider 或公开 trace。

达到这些条件，才是业务能力合并完成；“两个仓库的测试都通过”本身不是完成证据。
