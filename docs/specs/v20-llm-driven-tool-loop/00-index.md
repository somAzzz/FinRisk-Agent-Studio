# V20 LLM-driven Tool Loop Specs - Index

## 目标

V20 的目标是把 FinText-LLM 从“workflow 代码直接调用工具”逐步迁移到：

```text
LLM decides next tool
Backend validates and executes registered tool
Tool result returns as evidence/context
LLM continues or finishes
Workflow controls writes and quality gates
```

这不是把系统改成普通聊天机器人。它仍然是 evidence-first financial research workflow，只是把原 roadmap 中抽象的 `Tool Selection` 明确落地为标准 tool-calling agent loop。

## 与原始 roadmap 的关系

`docs/architecture-roadmap-cn.md` 规划了：

- 本地 LLM Agent 系统。
- Filing / Transcript / Web / Graph Agents。
- `web_search`、`web_fetch`、`browser_explore`、`graph_query`、`financial_metrics` 等工具。
- Neo4j 图谱和 evidence chain。
- Critic / guardrail / structured output。

V20 不改变这些目标。V20 补齐的是：

- provider-neutral tool loop。
- OpenAI-compatible `tools` schema。
- project-wide ToolCatalog。
- read tool / write tool 安全边界。
- workflow 迁移路径。
- 对本地 LLM 不支持 tool calling 的降级策略。

## Specs

按以下顺序执行：

1. [01 Tool Contract and Catalog](./01-tool-contract-and-catalog.md)
2. [02 Provider-neutral Tool Loop Runtime](./02-provider-neutral-tool-loop-runtime.md)
3. [03 Data Tools: SEC, Transcript, Financials](./03-data-tools-sec-transcript-financials.md)
4. [04 FinRisk Workflow Migration](./04-finrisk-workflow-migration.md)
5. [05 Supply Chain Workflow Migration](./05-supply-chain-workflow-migration.md)
6. [06 Graph, Browser, and Write Boundaries](./06-graph-browser-and-write-boundaries.md)
7. [07 Observability, Evaluation, and Local LLM Fallback](./07-observability-evaluation-local-fallback.md)
8. [08 Acceptance Roadmap](./08-acceptance-roadmap.md)

## 当前基线

已完成并提交的 V20 baseline：

- `src/llm/tool_loop.py`
- `src/llm/deepseek_client.py` tool loop 接入
- `src/llm/client.py` 本地 OpenAI-compatible tool loop 接入
- `src/tools/catalog.py` 第一版 catalog
- `src/agents/llm_runtime.py` 最小 LLM-driven runtime
- tests:
  - `tests/llm/test_tool_loop.py`
  - `tests/llm/test_deepseek_client.py`
  - `tests/llm/test_client.py`
  - `tests/tools/test_tool_catalog.py`
  - `tests/agents/test_llm_runtime.py`

## 总体迁移原则

1. Read tools first：先开放搜索、抓取、SEC 查询、transcript、financial metrics、graph read。
2. Writes stay gated：写 Neo4j、写 DB、生成报告、更新 memory 必须由 workflow/guardrail 控制。
3. Evidence-first：工具输出必须可转成 evidence 或 context manifest。
4. One catalog：DeepSeek、本地 LLM、fallback JSON router 使用同一份 ToolCatalog。
5. Deterministic core remains：实体归一化、evidence binding、graph write、risk scoring 仍由确定性代码控制。
6. Local-first：本地 vLLM/SGLang 是一等路径；DeepSeek/OpenAI-compatible API 是同协议 provider。
7. Trace everything：每一轮 tool call、工具参数、工具结果摘要、LLM final answer 都进入 trace。

## 分阶段落地

### Phase 0 - Baseline

状态：已完成。

目标：

- DeepSeek 与本地 OpenAI-compatible LLM 共用 tool loop。
- 暴露 `web_search`、`web_fetch`、`search_and_fetch`。
- 新增最小 `LLMToolAgentRuntime`。

### Phase 1 - Tool Contract Hardening

目标：

- 所有 LLM-visible tools 使用统一 `ProjectTool` 描述。
- 每个工具有 OpenAI-compatible schema、Python callable、output serializer、risk level、budget policy。
- ToolCatalog 支持按 workflow/agent/context 选择工具子集。

### Phase 2 - Data Tool Expansion

目标：

- 新增 `sec_list_filings`、`sec_fetch_filing`。
- 新增 `transcript_lookup`。
- 新增 `financial_metrics_lookup`。
- 新增 `xbrl_fact_lookup`。

### Phase 3 - FinRisk Workflow Migration

目标：

- `MarketExplorerStep` 迁移到 LLM 选择 `web_search` / `web_fetch` / `search_and_fetch`。
- `FilingRiskExtractorStep` 可请求 SEC filing 工具，但风险抽取仍保持 schema validation。
- Report generator 引用 LLM tool trace 和 evidence manifest。

### Phase 4 - Supply Chain Workflow Migration

目标：

- `SupplierDiscoveryStep` 由 LLM 选择 search/fetch/transcript/financial metrics。
- supplier edge 写入仍由 deterministic extractor + evidence guardrail 控制。
- 每条 confirmed edge 必须有 evidence。

### Phase 5 - Graph and Browser Integration

目标：

- 暴露 `graph_query` / `graph_path_search` read-only 工具。
- 暴露 `browser_explore` 高级工具。
- 禁止主 LLM 直接调用低层 browser click/type。

### Phase 6 - Fallback and Production Hardening

目标：

- 本地 LLM 不支持 native `tool_calls` 时，使用 JSON ToolChoice fallback。
- tool budget、provider budget、max rounds、max fetch pages 全部配置化。
- trace 可在 API/frontend 中展示。

## 完成定义

V20 完成时，应支持：

```bash
uv run python -m src.pipelines.llm_tool_research \
  --provider deepseek \
  --query "Find evidence about Apple's supply chain risk and cite sources."
```

以及本地 LLM：

```bash
uv run python -m src.pipelines.llm_tool_research \
  --provider vllm \
  --base-url http://localhost:8000/v1 \
  --model Qwen/Qwen3.5-35B-A3B \
  --query "Research NVIDIA data center supply chain dependencies."
```

验收：

- LLM 至少能自主选择 2 种不同工具。
- 工具 trace 可审计。
- final answer 区分 evidence / inference / uncertainty。
- 没有 write tool 直接暴露给 LLM。
- `uv run pytest -q` 通过。
