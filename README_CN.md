# FinRisk Agent Studio

Evidence-first agent workflow for SEC filing analysis, market evidence collection, graph reasoning, product supply-chain exploration, runtime quality guardrails, and human review.

FinRisk Agent Studio 是一个面向金融研究的 evidence-first agent workflow 开源参考实现。它不是通用的 "chat with filings" 演示,而是强调可审计执行:结构化输入、工具 trace、证据候选、确定性打分、图路径、质量门禁与人工复核。

> 英文 `README.md` 是主文档。本中文版同步核心结构、运行方式与最新进展;终端命令、API 路径、环境变量和模型名保持英文。

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
- **LLM-driven agent runs**: `/agent-runs` API,支持 provider/tool-loop 设置、tool traces、evidence candidates、redacted trace download 与 human review actions。
- **Provider-neutral tool loop**: OpenAI-compatible structured outputs、native tool calling、JSON fallback、budget controls 与 no-tool finalization。
- **Evidence and data tools**: SEC EDGAR、filing sections、transcripts、XBRL/financial metrics、web search/fetch、browser exploration、search routing、caching 与 provider fallback。
- **Memory/context guardrails**: evidence-memory adapters、graph-edge memory、active/candidate lifecycle rules 与 memory write guardrails。
- **Deployment path**: GitHub Pages 静态 dashboard 已发布;本地 full-stack 模式运行 FastAPI + Vite。

## Current Workflow Shape(工作流形态)

```text
Company Resolver
→ Filing Risk Extraction
→ Market Evidence Collection
→ Evidence Normalization
→ Risk Scoring
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
npm install
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

Vite dev server 会把 `/workflows`、`/supply-chain`、`/agent-runs` 代理到 FastAPI 后端。

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
POST /agent-runs/{run_id}/review-items/{item_id}
POST /agent-runs/{run_id}/evidence-candidates/{candidate_id}

GET  /research/financials/{ticker}
GET  /research/management/{ticker}
POST /research/valuation/scenarios
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
├── llm/               # OpenAI-compatible clients and tool-loop runtime
├── memory/            # evidence/graph memory and context guardrails
├── reports/           # report models and markdown renderer
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

- **Risk Studio 整改已完成**：Quality Layer 已成为 runtime gate，graph payload、report model、scoring 与 safety checks 由测试固定。
- **供应链研究能力已完成并加固**：Sankey model、recursive expansion、real SearchRouter path、graph writer、observability 与 frontend integration 已落地。
- **Context guardrail layer 已启动**：memory adapters、ingestion、graph-edge memory 与 memory write guardrails 已有最小工程切片。
- **Tool loop 已实现**：provider-neutral tool catalog、OpenAI-compatible tool loop、budget controls、data tools 与 JSON fallback。
- **Agent runtime 持续完善**：`/agent-runs` API、global runtime、evidence candidates、review gates、redacted trace download 与 frontend trace UI。
- **Local E2E validated**: 记录过真实 FinRisk、supply-chain 与 agent-run flows,覆盖 local SGLang、FastAPI、Vite 与 Neo4j-compatible paths。
- **GitHub Pages published**: 静态 dashboard 已上线。

相关记录:

- [文档中心](docs/README.md)
- [当前分析师工作台路线图](docs/current/analyst-workbench-roadmap.md)
- [Risk Studio 整改总结](docs/specs/v17-code-audit-remediation/07-completion-summary.md)
- [供应链研究能力完成总结](docs/specs/v18-product-supply-chain-sankey/07-completion-summary.md)
- [供应链生产化加固进度](docs/specs/v18-product-supply-chain-sankey/09-production-hardening-progress.md)
- [本地 LLM 端到端验证](docs/history/reports/validation/local-llm-e2e-api-frontend-2026-06-27.md)
- [Agent 系统差距审计](docs/history/reports/audits/agent-system-gap-report-2026-06-27.md)

## Testing(测试)

```bash
uv run pytest -q
```

```bash
cd frontend
npm test
npm run build
```

## Roadmap(路线图)

当前重点是 production hardening,而不是证明 workflow 概念:

1. 为 workflows、supply-chain runs、agent runs 增加持久化 run store。
2. 完成真实 Neo4j integration smoke tests。
3. 用带 evidence guardrails 的 structured LLM/NLI extractor 替换部分 rule-based supply-chain decomposition / supplier relation extraction。
4. 强化 provider budget controls: max calls、timeout、retry、cache TTL、cost estimate。
5. 继续收紧 browser exploration timeout、backend health 与 trace metadata。
6. 扩展 agent golden cases、evidence candidate quality 与 human-review outcome 评估。
7. 保持 GitHub Pages demo 与本地 dashboard 能力同步。

## Non-Goals(非目标)

- 不提供直接投资建议。
- 不给买卖推荐。
- 不允许 LLM-only confirmed graph edges。
- Demo mode 不要求 GPU、API keys、live browser success 或 live Neo4j。
- 不把通用 chatbot UI 作为主要入口。

## License(许可)

本项目包含 Yahoo Finance 数据,按 ODC-BY 授权。
