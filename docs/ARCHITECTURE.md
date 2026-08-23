# FinRisk Agent Studio v0.1 架构

## 产品定义

FinRisk Agent Studio 是面向个人金融分析师的 evidence-first 研究工作台。它围绕“发现变化、验证证据、维护假设、完成复盘”组织产品，而不是把内部 Agent 名称作为主要信息架构。

## 产品域

```text
Today
├── Needs review
├── Recent activity
└── Start research

Company
├── Overview
├── Risks
├── Financials
├── Valuation
├── Management
├── Supply Chain
└── Evidence

Research Runs
├── Run history
├── Tool trace
├── Evidence candidates
└── Human review

Journal
├── Research cycle
├── Thesis
├── Watchlist
├── Expectations
├── Peer analysis
└── Post-earnings review
```

## 系统结构

```text
React / Vite Workbench
        │
        ▼
FastAPI
├── /workflows       FinRisk 风险工作流
├── /supply-chain    产品供应链研究
├── /agent-runs      Tool Loop 与人工复核
└── /research        Snapshot、Journal、Peer、Valuation、Monitor
        │
        ▼
Application Services
├── workflows        编排、状态、质量门禁
├── agents / ai      planner、Pydantic AI runtime、provider adapter
├── research         财务、变化、Thesis、估值、监控
├── supply_chain     供应链发现、递归扩展、Sankey
├── graph_reasoning  路径检索、评分、证据绑定、解释验证
├── evidence/memory  候选证据、上下文与记忆生命周期
└── reports          结构化报告与 Markdown
        │
        ▼
Data and Providers
├── SEC / EDGAR / XBRL
├── Transcript providers
├── Web search / fetch / browser
├── OpenAI-compatible LLMs
├── SQLite research stores
└── Neo4j-compatible graph
```

## FinRisk 工作流

```text
Company Resolver
→ Filing Risk Extraction
→ Market Evidence Collection
→ Evidence Normalization
→ Risk Scoring
→ Graph Reasoning
→ Structured Report
→ Quality Layer / Human Review Gate
```

终态为 `completed | needs_review | failed`。`needs_review` 表示运行完成但存在证据、来源或安全问题，需要人工判断。

## 图推理边界

```text
Graph Context Builder
→ Candidate Path Retriever
→ Path Scorer
→ Evidence Binder
→ Path Interpreter
→ Graph Insight Validator
```

- LLM 只能解释已验证路径。
- 每个 confirmed edge 必须引用证据。
- hypothesis/candidate edge 与 confirmed edge 分开存储。
- 缺失路径或证据时返回空结果或 review finding，不生成补全事实。

## 研究数据模型

```text
Workflow Run
  └── CompanyResearchSnapshot (immutable)
       ├── Financial facts
       ├── Management observations
       ├── Risk observations
       ├── Supply-chain observations
       └── Source manifest

Snapshot A + Snapshot B
  └── ResearchChange
       ├── before / after
       ├── evidence IDs
       ├── materiality
       └── review status

Journal
├── InvestmentThesis
├── WatchlistItem
├── ExpectationPoint
├── ResearchAlert
├── PeerGroup
└── PostEarningsReview
```

所有模型遵守 point-in-time：`as_of` 之后发布的数据不能回写到旧快照或旧预期。

## 证据类型

| 类型 | 含义 |
| --- | --- |
| reported | 来源直接报告的事实 |
| derived | 有公式和输入 lineage 的派生值 |
| provider | 外部数据服务返回的值 |
| user-entered | 用户输入的假设或预期 |
| model interpretation | 模型对已验证证据的解释 |

界面和 API 必须保留类型差异，不得把用户假设或模型解释显示为 reported fact。

## 存储

- Workflow 与 Agent run 使用运行存储和 trace。
- Pydantic AI message history 使用版本化 append-only batch；run ID 与
  conversation ID 分离，resume 会生成新 run ID。
- Research Snapshot 与 Journal 默认使用两个 SQLite 数据库。
- 数据库通过 schema migration、事务、幂等升级和在线 backup API 管理。
- Neo4j 是可选图后端；demo/CI 可使用 fixture 或兼容内存路径。
- 静态 GitHub Pages 使用明确的离线 fixture，不发起伪实时请求。

## 运行模式

| 模式 | 数据 | 适用场景 |
| --- | --- | --- |
| demo | 固定 fixture | 无密钥演示、CI |
| cached | 已缓存证据优先 | 可复现研究 |
| live | 真实 provider | 本地/集成验收 |
| static frontend | 产品 fixture | GitHub Pages |

trace 必须记录 fallback 原因。静态或 cached 结果不能标记为 live。

### Pydantic AI Agent 运行时

Pydantic AI 是唯一模型调用与 Agent 运行时，负责 provider/model、typed dependency、
structured output、toolset、usage 和 message protocol。Browser Explorer 的页面摘要
与有界浏览器动作循环同样使用 typed Agent/tool；项目继续
负责 evidence、预算、审批、run-store、quality gate、业务状态机和 API contract。
FinRisk 与 Supply Chain 默认通过保持原 state contract 的 Pydantic Graph 执行；
API、CLI 与后台任务共用同一 Graph 入口，不再维护重复的手写 step 循环。
`/agent-runs` 的 planner → subgoal → planner 控制流也由独立 Pydantic Graph
执行，项目预算、evidence normalization 和 human-review 策略作为 Graph deps 保留。

`AGENT_RUNTIME_MODE` 已退役；新 run 统一记录 `pydantic_ai`。旧持久化记录的
runtime mode 仍可解析，但不能恢复已删除实现。LLM 服务由外部系统管理，本仓库
Compose 只包含 Neo4j。完成记录见 [迁移文档](PYDANTIC_AI_MIGRATION.md)。

## 安全与质量

- API 默认使用 `FINRISK_API_KEYS` 和 `X-API-Key`。
- Web fetch 经过 SSRF guard、协议和地址检查。
- Agent trace 下载会脱敏密钥和敏感字段。
- 质量门禁检查 schema、grounding、来源质量、财务安全、图路径和禁用建议语言。
- 项目不提供直接投资建议或交易执行。

## 代码目录

```text
src/
├── agents/
├── ai/
├── api/
├── browser/
├── data/
├── evaluation/
├── evidence/
├── graph/
├── graph_reasoning/
├── memory/
├── reports/
├── research/
├── supply_chain/
├── tools/
└── workflows/

frontend/
tests/
config/
deploy/
docs/
```
