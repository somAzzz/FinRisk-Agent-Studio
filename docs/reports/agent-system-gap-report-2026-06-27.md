# LLM-driven Agent System 当前状态与缺口报告

日期：2026-06-27

## 结论摘要

当前项目已经从“架构原型”推进到“本地真实案例可运行的 LLM-driven agent 系统雏形”。DeepSeek、Tavily、SEC EDGAR、transcript/metrics、Playwright browser backend、`/agent-runs` runtime、tool trace、evidence normalizer、human review、golden case evaluation 都已经有真实代码路径。

但它还不是完整生产级 agent system。最新真实测试显示：系统可以完成 Apple supply-chain risk 这类真实案例，但 graph、部分外部 provider、browser latency、tool budget、长期 run storage、live benchmark 等仍是主要缺口。

最近验证结果：

```text
853 passed, 7 skipped
```

最新真实测试产物：

- `docs/reports/live-agent-apple-supply-chain-trace.json`
- `docs/reports/live-agent-run-apple-supply-chain-trace.json`

## 最新真实测试观察

### CLI tool-loop 真实案例

入口：

```bash
uv run python -m src.pipelines.llm_tool_research \
  --provider deepseek \
  --tools finrisk_market \
  --query "Find evidence about Apple's supply chain risk and cite sources."
```

观察：

- DeepSeek native tool loop 可以真实调用工具。
- Trace 中出现 `sec_list_filings`、`web_search`、`financial_metrics_lookup`、`sec_fetch_filing`、`transcript_lookup`、`web_fetch`、`search_and_fetch`、`xbrl_fact_lookup`、`browser_explore`。
- `web_search` 已能走 Tavily provider。
- SEC EDGAR 真实 smoke 已验证：AAPL ticker 可映射 CIK，filings/company concept 可返回真实数据。
- `browser_explore` 在真实网页中可运行，但一次探索耗时约百秒，说明 browser tool 需要更严格的超时和预算门禁。
- Trace 中 `budget_usage.used_tool_result_chars` 曾超过 `max_total_tool_result_chars`；本轮已修复总工具结果预算门禁，后续真实案例需要复跑确认。

### `/agent-runs` 真实案例

观察：

- `/agent-runs` 已不是 plan-only，默认路径可构建 `GlobalAgentRuntime` 并执行真实 tool loop。
- 一次 Apple supply-chain 风险案例完成状态为 `completed`。
- 真实 tool events 包括 `sec_list_filings`、`sec_fetch_filing`、`transcript_lookup`、`web_search`。
- 证据归一化可产出 accepted / needs_review / rejected evidence candidates。
- 低层 browser action 和 raw Cypher 没有暴露给 LLM。

## 已关闭或显著收敛的缺口

### 已修复：`/agent-runs` 默认 plan-only

文件：

- `src/api/agent_runs.py`

当前状态：

- API 请求可以通过 runtime factory 复用 `src.pipelines.llm_tool_research.build_runtime(...)`。
- Request 已支持 `provider`、`tool_loop_mode`、`tool_scope`、`max_tool_rounds`、`model`、`base_url` 等参数。
- `set_agent_runtime_for_tests()` 仍保留给测试注入。

剩余风险：

- API route 仍以同步方式执行长 agent run，真实长任务可能阻塞服务线程。后续需要 background job / worker / async offload。

### 已修复：Browser backend 依赖单一 `agent-browser` CLI

文件：

- `src/browser/factory.py`
- `src/browser/playwright_wrapper.py`
- `src/browser/explorer.py`
- `src/tools/router.py`

当前状态：

- 默认 `BROWSER_BACKEND=playwright`。
- Playwright wrapper 已可真实打开页面并抽取内容。
- `agent-browser` 保留为 fallback backend。

剩余风险：

- `browser_explore` 仍可能耗时过长。
- 需要把 browser timeout、max steps、backend health、trace backend source 纳入 agent tool budget。

### 已修复：Tavily 与 SEC 基础配置

文件：

- `.env.example`
- `src/config.py`
- `src/data/sec_client.py`

当前状态：

- `.env.example` 已包含 `TAVILY_API_KEY`、`SEARCH_PROVIDER_ORDER`、`SEC_USER_AGENT`。
- SEC helper 已支持 company tickers、ticker -> CIK、company concept、filing document URL。
- 本地 `.env` 已配置 Tavily 和 SEC user agent。

注意：

- 不应把 `.env` 或任何 API key 写入报告、trace 或 README。
- SEC 不需要 API key，但需要合规 User-Agent 和低于 SEC 指引的请求速率。

### 已修复：Tool loop 在 max rounds 后抛错

文件：

- `src/llm/tool_loop.py`

当前状态：

- Native tool loop 与 JSON fallback 都会在 max rounds 用无工具 final prompt 收束答案。
- 不再因为模型持续请求工具而直接抛出 `ToolLoopError`。

### 已修复：async tool / web fetch 在已有 event loop 中的问题

文件：

- `src/llm/tool_loop.py`
- `src/tools/web_fetch.py`
- `src/tools/search_router.py`

当前状态：

- Sync tool loop 可以执行 awaitable tool。
- `web_fetch_sync` 和 search fetcher 可以在已有 event loop 中安全运行。

### 已修复：截断 SEC filing event 难以进入 evidence normalizer

文件：

- `src/evidence/candidates.py`

当前状态：

- Truncated SEC filing / XBRL / transcript 等 tool result 可以做部分恢复。
- Filing 和 financial metric 的跨语言 grounding 过低问题已有保护。

## 仍然存在的主要缺口

### 本轮已部分修复：Graph tools 不再默认静默返回 fixture

文件：

- `src/tools/catalog.py`
- `.env.example`
- `src/graph/client.py`
- `src/graph_reasoning/backends.py`

当前状态：

- `graph_query` / `graph_path_search` tool schema 已受控。
- 本轮已修改默认行为：如果没有注入 graph backend，graph tools 返回 `graph_source: unavailable`、空 `paths` 和明确错误说明。
- Fixture graph 只有在 `GRAPH_TOOL_ALLOW_FIXTURE=1` 时才会暴露给 LLM-visible tools。
- Tool result 会记录 `graph_source`：`unavailable`、`fixture`、`neo4j` 或注入 backend 名称。
- 最新 `/agent-runs` 真实案例为了避免虚假图推理，没有调用 graph tools。

影响：

- 默认路径不会再给真实案例返回 AAPL/TSMC fixture 假图。
- 对非 fixture 企业或复杂供应链二阶风险，仍需要真实 Neo4j backend 才能产生生产级图证据。

剩余风险：

- 默认从 `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` 构建 graph backend。
- 统一 `src.graph.client.Neo4jClient` 与 graph tool backend 的接口。
- 增加 Neo4j live smoke / mock backend 测试。

验证：

```text
uv run pytest tests/tools/test_graph_browser_tool_boundaries.py -q
5 passed
```

### 本轮已部分修复：Supply Chain graph write 可从 env 初始化 Neo4j

文件：

- `src/supply_chain/steps/graph_builder.py`
- `tests/supply_chain/test_graph_builder.py`

当前状态：

- `SupplyChainGraphBuilderStep` 仍支持手动注入 `graph_client`。
- 本轮已增加 env 初始化：当 `NEO4J_PASSWORD` 有真实值且不是 `REPLACE_ME` 时，会尝试创建 `Neo4jClient()`。
- 没有配置或创建失败时，real mode 会在 `fallback_events` 中记录明确原因，然后使用 in-memory graph。
- Demo/cached mode 仍保持静默 fallback，避免离线 demo 噪声。

影响：

- 本地配置 Neo4j 后，Supply Chain workflow 可以进入真实写图路径。
- 未配置 Neo4j 时，不再只有模糊的 “client unavailable”，而是能看到缺少环境变量或连接失败原因。

剩余风险：

- 还需要真实 Neo4j integration smoke 来验证 schema 与写入结果。
- graph read tools 仍需要统一真实 backend factory，才能复用写入后的供应链图。

验证：

```text
uv run pytest tests/supply_chain/test_graph_builder.py -q
2 passed
```

### 本轮已修复：Tool result 总预算门禁严格化

文件：

- `src/llm/tool_loop.py`

当前状态：

- 单工具结果可以截断。
- 本轮已修复 `_truncate_content(...)`，tool content 不再超过 `max_result_chars`。
- Native 和 JSON fallback 都已在执行工具前检查 `remaining_budget`。
- 预算耗尽时不会继续执行工具，而是生成 `failed` tool event，提示模型基于已有证据 final answer。
- 新增测试覆盖预算耗尽后第二个工具不会被调用。

验证：

```text
uv run pytest tests/llm/test_tool_loop.py tests/llm/test_tool_loop_fallback.py -q
11 passed
```

### 本轮已部分修复：Browser explore 超时、降级和 trace metadata

文件：

- `src/tools/catalog.py`
- `src/browser/playwright_wrapper.py`
- `src/browser/explorer.py`
- `tests/tools/test_graph_browser_tool_boundaries.py`

当前状态：

- Playwright backend 可运行。
- 真实案例显示 `browser_explore` 可能显著拉长 run time。
- 本轮已给 `browser_explore` schema 增加 `timeout_seconds`。
- Tool wrapper 已增加外层 timeout，超时后返回 `timed_out: true`、`error`、`browser_backend`、`max_steps`、`timeout_seconds`，不会继续阻塞 agent loop 等待结果。
- 新增测试覆盖超时降级路径。

剩余风险：

- 外层 timeout 无法强杀已经进入底层浏览器的 daemon thread，只能让 agent loop 先返回。
- 仍需要 planner/tool policy 默认优先 `web_search` / `web_fetch`，只有遇到 JS-heavy 页面或 search/fetch 失败时再调用 browser。
- 后续可继续在 `MarketExplorer` 内部增加 page budget、max pages、每步 timeout。

验证：

```text
uv run pytest tests/tools/test_graph_browser_tool_boundaries.py -q
5 passed
```

### 本轮已部分修复：Search quality filter 初版

文件：

- `src/tools/search_router.py`
- `src/tools/providers/`
- `tests/tools/test_search_router.py`

当前状态：

- Tavily 可用，DuckDuckGo 可 fallback。
- 真实结果中仍可能出现社交媒体、低质量聚合页、无关页面。
- 本轮已在 `SearchRouter` 返回结果前增加 source quality ranking。
- Facebook、Instagram、Pinterest、TikTok、Threads、LinkedIn posts、YouTube Shorts 等低质量社交结果会被过滤。
- SEC、Reuters、Bloomberg、WSJ、FT、CNBC、MarketWatch、监管域名和公司 IR 相关路径会被加权前置。
- SearchResult metadata 会写入 `source_quality_score` 和 `source_quality_reason`，方便 trace 审计。

剩余风险：

- Domain list 仍需通过更多 live cases 调参。
- 还没有根据 query intent 动态切换 domain preference。

验证：

```text
uv run pytest tests/tools/test_search_router.py -q
22 passed
```

### P1：Transcript / metrics provider router 不完整

文件：

- `src/tools/catalog.py`
- `src/data/providers/defeatbeta.py`
- `src/data/providers/fmp.py`
- `src/data/providers/alpha_vantage.py`

当前状态：

- `transcript_lookup` / `financial_metrics_lookup` 默认主要依赖 DefeatBeta。
- FMP / Alpha Vantage provider 已存在，但还不是统一优先链。

建议修复：

- 增加 transcript / metrics provider router。
- Trace 记录 provider、fallback reason、coverage status。
- 可配置优先级：DefeatBeta、FMP、Alpha Vantage、cache。

### P1：Evidence normalizer 仍应优先消费结构化原始结果

文件：

- `src/evidence/candidates.py`
- `src/llm/tool_loop.py`
- `src/schemas/tool_trace.py`

当前状态：

- Normalizer 已能从截断文本中部分恢复。
- 但最佳路径应该是在 truncation 前保留结构化 evidence payload 或 canonical rows。

影响：

- 截断越激进，证据归一质量越依赖启发式恢复。

建议修复：

- Tool event 增加可选 `structured_summary` 或 `evidence_rows`。
- Normalizer 优先消费结构化 rows，再 fallback 到文本恢复。

### P1：API long-running agent run 需要 job 化

文件：

- `src/api/agent_runs.py`
- `src/api/run_store.py`
- `src/api/store_factory.py`

当前状态：

- `/agent-runs` 可真实执行 runtime。
- 但长 agent run 仍在请求路径内执行。
- 默认 run storage 仍偏内存。

建议修复：

- 增加 `AgentRunStore`。
- 支持 `RUN_STORE_BACKEND=sqlite`。
- `POST /agent-runs` 返回 run id，后台执行；`GET /agent-runs/{id}` 轮询状态。

### P2：Live benchmark 仍需正式化

文件：

- `src/evaluation/agent_eval.py`
- `tests/fixtures/agent_golden_cases/`

当前状态：

- Fixture golden cases 可防回归。
- 真实 DeepSeek/search/browser/SEC live smoke 主要是手动执行。

建议修复：

- 增加显式 live 开关：

```text
RUN_AGENT_LIVE=1
RUN_DEEPSEEK_LIVE=1
RUN_SEARCH_LIVE=1
RUN_BROWSER_LIVE=1
RUN_NEO4J_LIVE=1
```

- Live tests 默认 skip，必须有 timeout、budget、redaction。

### P2：Trace redaction 可能过度遮蔽 SEC public identifiers

当前状态：

- Trace redaction 会保护 API key/token。
- 真实 trace 中 public identifiers 如 CIK/accession 可能被误识别为敏感数字。

建议修复：

- 区分 secret、phone-like number、SEC CIK/accession。
- SEC public identifiers 不应影响证据可追溯性。

## 当前环境变量填充优先级

### DeepSeek

```text
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### Local LLM

```text
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_API_KEY=dummy
VLLM_MODEL=...
LOCAL_LLM_TOOL_LOOP_MODE=auto
```

或：

```text
OPENAI_BASE_URL=http://localhost:30000/v1
OPENAI_API_KEY=EMPTY
LLM_PROVIDER=sglang
LOCAL_LLM_TOOL_LOOP_MODE=auto
```

### Web Search

```text
SEARCH_PROVIDER_ORDER=tavily,duckduckgo
TAVILY_API_KEY=...
BRAVE_API_KEY=...
EXA_API_KEY=...
SERPER_API_KEY=...
SERPAPI_API_KEY=...
```

### SEC EDGAR

```text
SEC_USER_AGENT=Your Name your.email@example.com
SEC_RATE_LIMIT_PER_SECOND=5
```

### Browser

```text
BROWSER_BACKEND=playwright
```

### Neo4j

```text
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
```

## 推荐逐一修复顺序

1. 增加真实 Neo4j backend factory，并统一 graph tool backend 接口。
2. 增加 transcript / metrics provider router。
3. 增加结构化 evidence rows，减少 normalizer 对截断文本的依赖。
4. 将 `/agent-runs` 长任务 job 化，并接入 sqlite run store。
5. 增加 live smoke test harness。

## 风险判断

当前系统适合：

- 本地真实案例 smoke test。
- DeepSeek/local LLM tool calling 验证。
- FinRisk / Supply Chain agent architecture 验证。
- Evidence-first trace/review/eval 验证。

当前系统还不适合：

- 无人工确认地生成生产级投资/风控结论。
- 依赖 fixture graph 做非 AAPL 示例的真实二阶风险结论。
- 在未配置稳定 search/browser/graph/provider 前做大规模真实数据评估。
- 长时间公网 API 服务；用户当前也已说明不打算公网部署 API。
