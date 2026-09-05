# FinRisk Agent Studio

面向个人金融研究的 evidence-first 工作台，覆盖 SEC filing、point-in-time 公司快照、同行比较、估值、监控、图推理、供应链、质量门禁与人工复核。

FinRisk Agent Studio 是一个面向金融研究的 evidence-first agent workflow 开源参考实现。它不是通用的 "chat with filings" 演示,而是强调可审计执行:结构化输入、工具 trace、证据候选、确定性打分、图路径、质量门禁与人工复核。

> 英文 `README.md` 是主文档。本中文版同步核心结构、运行方式与最新进展;终端命令、API 路径、环境变量和模型名保持英文。

当前文档版本：**v0.1 release candidate**；Python 与前端包版本：`0.1.0`。

## Live Demo

```text
https://somazzz.github.io/FinRisk-Agent-Studio/
```

GitHub Pages 托管版是基于离线 fixtures 的静态 dashboard。它展示 FinRisk workflow timeline、risk report、evidence graph、score breakdown 与 evaluation guardrails,不要求 API key、后端服务、GPU、Neo4j 或实时网络。

## What Works Today(当前已实现)

- **FinRisk workflow API**: FastAPI queued/background run,覆盖 SEC filing risk extraction、market evidence、normalization、scoring、graph reasoning、report generation 与 evaluation。
- **Runtime quality layer**: schema checks、claim/evidence grounding、source quality、financial-safety checks、graph-path validation、fallback tracking 与 human-review status。
- **Graph reasoning subsystem**: context building、candidate path retrieval、path scoring、evidence binding、safe path interpretation 与 graph insight validation。
- **React workflow console**: launcher、run history、process monitor、timeline、risk report、score breakdown、evidence graph、evaluation panel、claim/evidence matrix、supply-chain explorer 与 agent-run trace UI。
- **Product supply-chain explorer**: evidence-backed product dependency discovery、recursive expansion、Sankey visualization、graph writer path、observability metrics 与 quality verdicts。
- **LLM-driven agent runs**: `/agent-runs` API,支持 Pydantic AI provider 设置、tool traces、evidence candidates、redacted trace download 与 human review actions。
- **Provider-neutral Agent runtime**: Pydantic AI structured outputs、typed tools、budget controls、usage accounting 与可审计终态。
- **Evidence and data tools**: SEC EDGAR、filing sections、transcripts、XBRL/financial metrics、web search/fetch、browser exploration、search routing、caching 与 provider fallback。
- **Memory/context guardrails**: evidence-memory adapters、graph-edge memory、active/candidate lifecycle rules 与 memory write guardrails。
- **个人研究闭环**：不可变快照、Thesis/Watchlist、预期、重大变化复核、提醒、财报后复盘，以及 FinRisk 直接关联研究快照。
- **财务事实层**：可审计 alias、六类行业模板、original/amended/latest-known 查询、单季与 TTM 派生，以及 AAPL、NVDA、XOM、JPM、TSM 真实勾稽。
- **Peer Analysis**：持久化同行组、SEC SIC 候选与人工确认、财年/币种/新鲜度控制，以及财务、风险、预期、估值分层视图。
- **估值与监控**：情景估值、敏感性、P/E、EV/EBITDA、FCF yield、简化 DCF、假设历史、节流重试、来源 cursor 与本地调度模板。
- **Deployment path**: GitHub Pages 静态 dashboard 已发布;本地 full-stack 模式运行 FastAPI + Vite。

## Current Workflow Shape(工作流形态)

```text
Company Resolver
→ Filing Risk Extraction
→ Market Evidence Collection
→ Evidence Normalization
→ Risk Scoring
→ Risk Lifecycle Classification
→ Graph Reasoning
→ Structured Report Generation
→ Quality Layer / Human Review Gate
```

图推理作为受控子系统执行:

```text
Graph Context Builder
→ Candidate Path Retriever
→ Path Scorer
→ Evidence Binder
→ LLM / Template Path Interpreter
→ Graph Insight Validator
→ Evidence Graph Payload
```

LLM 只解释已验证路径并生成研究假设,不创建无证据图事实,也不输出买卖建议。

## Quick Start(快速开始)

安装 Python 依赖:

```bash
uv sync
```

安装前端依赖:

```bash
cd frontend
npm ci
```

启动后端:

```bash
AUTH_DISABLED=1 RATE_LIMIT_DISABLED=1 \
uv run uvicorn src.api.main:app --host 127.0.0.1 --port 8000
```

另开终端启动前端:

```bash
cd frontend
npm run dev
```

打开:

```text
http://127.0.0.1:5173/
```

Vite dev server 会把 `/workflows`、`/supply-chain`、`/agent-runs`、`/research` 代理到 FastAPI 后端。

首次运行或升级后迁移本地数据库：

```bash
uv run python main.py database migrate --path .cache/research_snapshots.sqlite
uv run python main.py database migrate --path .cache/research_journal.sqlite
```

## Static Dashboard Build(静态页面构建)

```bash
cd frontend
GITHUB_PAGES=true VITE_STATIC_DEMO=1 npm run build
npm run preview -- --host 127.0.0.1 --port 4173
```

## API Surface(API)

FastAPI 入口:

```bash
uv run uvicorn src.api.main:app --reload
```

核心 routes:

```text
GET  /
GET  /workflows/health
GET  /workflows
POST /workflows/finrisk/run
GET  /workflows/{run_id}
GET  /workflows/{run_id}/report
GET  /workflows/{run_id}/trace
GET  /workflows/{run_id}/graph
GET  /workflows/{run_id}/evaluation
GET  /workflows/{run_id}/artifacts
GET  /workflows/{run_id}/llm_log
GET  /workflows/{run_id}/chunks
GET  /workflows/{run_id}/sections
GET  /workflows/{run_id}/lifecycles

GET  /supply-chain
POST /supply-chain/explore
POST /supply-chain/expand
GET  /supply-chain/{run_id}
GET  /supply-chain/{run_id}/sankey

GET  /agent-runs
POST /agent-runs
GET  /agent-runs/{run_id}
GET  /agent-runs/{run_id}/timeline
GET  /agent-runs/{run_id}/trace.json
POST /agent-runs/{run_id}/resume
POST /agent-runs/{run_id}/review-items/{item_id}
POST /agent-runs/{run_id}/evidence-candidates/{candidate_id}

GET  /research/financials/{ticker}
GET  /research/management/{ticker}
POST /research/valuation/scenarios
POST /research/valuation/sensitivity
POST /research/valuation/multiple
POST /research/valuation/dcf
GET  /research/valuation/history/{ticker}
POST /research/runs
GET  /research/snapshots
GET  /research/changes/{ticker}
GET/POST /research/expectations
GET/POST /research/alerts
GET/POST /research/peer-groups
POST /research/peer-groups/{peer_group_id}/candidates
POST /research/peer-groups/{peer_group_id}/analysis
POST /research/monitor/scan
GET/POST /research/theses
GET/PUT  /research/watchlist
GET      /research/reminders
```

默认 API 通过 `FINRISK_API_KEYS` + `X-API-Key` 鉴权。本地开发可临时设置 `AUTH_DISABLED=1`。

## Architecture(架构)

```text
src/
├── agents/            # planner, global runtime, tool-driven agent state
├── api/               # FastAPI routes, auth, rate limit, run stores
├── browser/           # Playwright and agent-browser exploration backends
├── data/              # SEC, EDGAR, transcripts, XBRL, ticker resolution
├── evaluation/        # quality layer, validators, grounding, safety checks
├── evidence/          # evidence candidate normalization
├── graph/             # Neo4j-compatible graph clients, queries, writers
├── graph_reasoning/   # path retrieval, scoring, binding, validation
├── ai/                # Pydantic AI agents、model factory 与 typed clients
├── memory/            # evidence/graph memory and context guardrails
├── reports/           # report models and markdown renderer
├── research/          # 快照、研究日志、同行、估值与监控
├── supply_chain/      # product supply-chain workflow and Sankey payloads
├── tools/             # web/search/data/graph tool catalog
└── workflows/         # FinRisk workflow state、steps 与质量门控 runner

frontend/
docs/
tests/
```

## LLM Providers(LLM Provider)

| Provider | `LLM_PROVIDER` | Base URL | Auth env var | Example model |
|---|---|---|---|---|
| SGLang | `sglang` | `http://localhost:30000/v1` | `SGLANG_API_KEY` | `Qwen/Qwen3.5-35B-A3B` |
| vLLM | `vllm` | `http://localhost:8000/v1` | `VLLM_API_KEY` | `Qwen/Qwen3.5-35B-A3B` |
| OpenAI | `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | `gpt-4o-mini` |
| DeepSeek | `deepseek` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` | `deepseek-v4-flash` |

本地 stack:

```bash
docker compose up -d
```

Demo 和 CI 路径设计为不需要真实 API keys。

## Capability Progress（能力进展）

当前状态统一维护在 [v0.1 项目状态](docs/STATUS.md)：

- **已完成**：带质量门禁的 FinRisk 风险工作流和 point-in-time 个人研究闭环。
- **核心完成**：证据/数据基础、图与供应链研究、财务事实、同行分析、估值、监控和部署路径。
- **进行中**：长期 context/memory 质量、可恢复的无人值守 Agent、全仓 lint 治理和候选版本验证。
- **产品工作台已完成**：Today/Company/Runs/Journal 十条路由通过桌面/移动 QA、前端测试与生产构建。
- **v0.1 候选尚未发布**：仓库没有产品 tag，不能把代码候选描述成已发布的 `v0.1.0`。

当前文档：

- [文档中心](docs/README.md)
- [项目全景与面试讲法](docs/PROJECT_OVERVIEW_INTERVIEW_CN.md)
- [v0.1 项目状态](docs/STATUS.md)
- [路线图](docs/ROADMAP.md)
- [系统架构](docs/ARCHITECTURE.md)
- [v0.1 规格](docs/specs/v0.1.md)
- [财务勾稽](docs/validation/financial-reconciliation.md)
- [前端验收](docs/validation/frontend-acceptance.md)
- [Research Journal 本地 LLM 验收](docs/validation/research-journal-live.md)

## Testing(测试)

```bash
uv run pytest -q
```

```bash
cd frontend
npm test
npm run build
```

2026-09-03 本地复核：后端非集成测试 `976 passed, 8 deselected`；前端 18 个测试文件、76 tests；生产构建通过。三视口 Chromium、真实 vLLM、30/30 guardrail cases 与 `npm audit` 0 vulnerabilities 的最近记录日期为 2026-07-12。

## Roadmap(路线图)

v0.1 的近期发布路径是：在当前候选上重跑 CI、npm audit、浏览器 smoke 和真实模式验收，并明确是否创建首个 `v0.1.0` tag。

v0.2 聚焦 Agent memory、恢复、幂等、集成覆盖和 lint 治理；v0.3 增加分部、consensus、FX 和行业深度；v0.4 处理外部通知和长期校准。详见[版本化路线图](docs/ROADMAP.md)。

## Non-Goals(非目标)

- 不提供直接投资建议。
- 不给买卖推荐。
- 不允许 LLM-only confirmed graph edges。
- Demo mode 不要求 GPU、API keys、live browser success 或 live Neo4j。
- 不把通用 chatbot UI 作为主要入口。

## License(许可)

本项目包含 Yahoo Finance 数据,按 ODC-BY 授权。
