# Step 20 - LLM-driven Tool Calling Agent Loop

## 背景

当前项目已经有多套工具和 agent 结构：

- `src/tools/search_router.py`：统一搜索入口，封装 DuckDuckGo、Brave、Tavily 等 provider。
- `src/tools/web_fetch.py`：静态网页抓取与正文抽取。
- `src/browser/*`：浏览器探索能力。
- `src/data/*`：SEC filing、transcript、financial metrics 等数据入口。
- `src/agents/runtime.py`：规则式 planner + agent/tool dispatch。
- `src/tools/router.py`：旧版 JSON structured-output 工具选择器。

但这些能力目前大多由代码直接编排，或者由规则式 planner 选择，并不是标准的 OpenAI-compatible
tool calling loop。DeepSeek / OpenAI-compatible API 只会返回 `tool_calls`，不会自动执行本地函数。
因此系统需要一个统一的后端执行循环：

```text
LLM proposes tool_calls
        ↓
Backend validates tool names and args
        ↓
Backend executes local registered functions
        ↓
Backend appends role="tool" messages
        ↓
LLM continues until final answer
```

## 目标

把系统从“代码直接调用工具 / 规则式选择工具”升级为“LLM 决定何时调用工具，后端安全执行工具”的统一模式。

本步骤要解决：

1. DeepSeek 与本地 OpenAI-compatible LLM 共用同一套工具调用 loop。
2. 项目工具以统一 catalog 暴露给 LLM。
3. Search / Fetch / Browser / Filing 等读操作可以被 LLM 选择。
4. 写数据库、写图、改配置等状态变更继续由 workflow 控制，不直接暴露给 LLM。
5. 对不支持原生 `tool_calls` 的本地模型，后续可降级到 JSON 工具选择协议。

## 非目标

本步骤不做：

- 让 LLM 直接写 Neo4j、写 SQLite、修改 `.env` 或修改配置。
- 让主 LLM 直接执行任意 browser `click/type/scroll`。
- 一次性替换所有 FinRisk / Supply Chain workflow。
- 依赖真实外网测试作为 CI 必需项。
- 暴露 provider 原始 API key 或底层 provider client 给 LLM。

## 工具暴露策略

### 可以暴露给 LLM 的工具

| 工具名 | 后端实现 | 用途 |
|---|---|---|
| `web_search` | `SearchRouter.search` | 通用网页搜索，内部自动 provider fallback/cache |
| `web_fetch` | `web_fetch_sync` | 抓取指定 URL 正文和元数据 |
| `browser_explore` | `MarketExplorer.explore` | web_fetch 失败或页面需要交互时的高级工具 |
| `sec_list_filings` | `FilingFetcher.list_filings` | 查询公司 filing 列表 |
| `sec_fetch_filing` | `FilingFetcher.fetch_filing` | 拉取指定 filing 正文 |
| `financial_metrics_lookup` | `src/data/providers/*` | 查询财务指标或 ratios |
| `transcript_lookup` | `src/data/transcripts.py` | 查询电话会议文本 |

### 不应直接暴露给 LLM 的工具

| 能力 | 原因 |
|---|---|
| graph write / database write | 状态变更必须由 workflow 和 guardrail 控制 |
| file write / config write | 安全边界太大 |
| arbitrary browser click/type | 容易陷入不可控交互，应包装成 `browser_explore` 子 agent |
| provider raw client | 避免 LLM 选择错误 endpoint 或绕过统一缓存/限流 |
| prompt/policy mutation | 项目策略必须代码版本化 |

## 本地 LLM 策略

本地 LLM 通过 `EdgarLLMClient` 使用 OpenAI-compatible `/v1/chat/completions`。

### 原生 tool calling 路径

如果本地 vLLM/SGLang server 支持 OpenAI-compatible `tools` / `tool_calls`：

```text
EdgarLLMClient.chat_with_tools(...)
    → OpenAICompatibleToolLoop
    → local /v1/chat/completions
```

### 降级路径

如果本地模型不支持 tool calling：

```text
LLM emits JSON ToolChoice
    → backend validates against same ToolCatalog
    → backend executes tool
    → LLM synthesizes final answer
```

降级路径应复用同一个 `ToolCatalog` 和 `ToolExecutor`，避免 DeepSeek、本地 LLM、旧 router 三套工具定义漂移。

## 实施阶段

详细工程规格已拆分到：

```text
docs/specs/v20-llm-driven-tool-loop/
```

建议按以下 specs 顺序执行：

1. `00-index.md`
2. `01-tool-contract-and-catalog.md`
3. `02-provider-neutral-tool-loop-runtime.md`
4. `03-data-tools-sec-transcript-financials.md`
5. `04-finrisk-workflow-migration.md`
6. `05-supply-chain-workflow-migration.md`
7. `06-graph-browser-and-write-boundaries.md`
8. `07-observability-evaluation-local-fallback.md`
9. `08-acceptance-roadmap.md`

### Phase 1：统一工具调用内核

新增：

- `src/llm/tool_loop.py`

职责：

- 接收 OpenAI-compatible SDK client、model、provider。
- 发送 `tools` 和 `tool_choice`。
- 解析 `message.tool_calls`。
- 只执行 `tool_map` 中注册的函数。
- 将未知工具、坏 JSON、工具异常转成 `role="tool"` error message。
- 生成 `LLMCall` 审计记录。

完成定义：

```bash
uv run pytest tests/llm/test_tool_loop.py tests/llm/test_deepseek_client.py -q
```

### Phase 2：接入 DeepSeek 与本地 LLM

改造：

- `DeepSeekClient.complete_with_tools`
- `DeepSeekClient.chat_with_tools`
- `EdgarLLMClient.complete_with_tools`
- `EdgarLLMClient.chat_with_tools`

要求：

- DeepSeek 和本地 LLM 共享 `OpenAICompatibleToolLoop`。
- `DeepSeekClient` 保留 key 配置校验。
- `EdgarLLMClient` 不强制真实 key，继续支持 vLLM/SGLang 本地 dummy key。

### Phase 3：项目 ToolCatalog

新增：

- `src/tools/catalog.py`

第一版暴露：

- `web_search`
- `web_fetch`
- `search_and_fetch`

说明：

- `web_search` 使用 `SearchRouter`，而不是裸 DuckDuckGo / Tavily。
- provider 可作为可选参数，但默认 `auto`。
- `search_and_fetch` 是便利工具：先 search，再 fetch top N URLs。
- 输出必须 JSON-serializable。

### Phase 4：LLM Agent Runtime 第一版

新增或扩展：

- `src/agents/llm_runtime.py`

第一版职责：

- 接收 goal。
- 使用当前 provider 的 `chat_with_tools`。
- 注入 ToolCatalog。
- 返回 final answer、tool history、LLMCall audit log。

说明：

- 先不替换现有 deterministic workflow。
- FinRisk / Supply Chain 后续逐步接入。

### Phase 5：真实案例入口

新增一个可手动运行的 smoke/demo 命令或脚本：

```bash
uv run python -m src.pipelines.llm_tool_research --query "..."
```

第一版允许：

- 使用 DeepSeek。
- 使用本地 vLLM/SGLang。
- 只调用读工具。
- 输出工具调用 trace 和最终回答。

## 本轮落地范围

本轮优先完成 Phase 1-3，并为 Phase 4 留出最小 runtime 骨架：

1. 新增 provider-neutral `OpenAICompatibleToolLoop`。
2. DeepSeek 改为复用通用 loop。
3. `EdgarLLMClient` 支持同样的 `complete_with_tools` / `chat_with_tools`。
4. 新增 `ToolCatalog`，先暴露 `web_search`、`web_fetch`、`search_and_fetch`。
5. 添加单元测试覆盖：
   - 工具执行成功。
   - 未知工具不执行。
   - 强制 `tool_choice` 只用于第一轮。
   - 本地 `EdgarLLMClient` 会把 `tools` 传给 OpenAI-compatible server。
   - ToolCatalog 输出 OpenAI-compatible schema。

## 验证命令

```bash
uv run ruff check src/llm src/tools tests/llm tests/tools
uv run pytest tests/llm/test_tool_loop.py tests/llm/test_deepseek_client.py tests/llm/test_client.py tests/tools/test_tool_catalog.py -q
uv run pytest -q
```

真实 DeepSeek smoke test 可手动执行，但不进入默认 CI。

## 风险与缓解

- 风险：本地 server 不支持原生 tool calling。
  - 缓解：保留 JSON ToolChoice 降级路线，后续复用 ToolCatalog。
- 风险：LLM 选择过多 search/fetch 造成成本或延迟。
  - 缓解：`max_tool_rounds`、`max_results`、`max_pages`、cache 和 provider budget。
- 风险：LLM 请求危险 URL。
  - 缓解：继续复用 `web_fetch` / `BrowserWrapper` 的 SSRF guard。
- 风险：工具输出太长。
  - 缓解：ToolCatalog 中做裁剪和 summary。

## 后续接入点

Phase 1-3 完成后，优先接入：

1. `MarketExplorerStep`：从直接 `SearchRouter.search` 升级为 LLM 选择 `web_search` / `web_fetch`。
2. `SupplyChainSupplierDiscoveryStep`：让 LLM 决定何时搜索、何时 fetch，但 supplier edge 写入仍由 deterministic extractor 控制。
3. 新增真实案例 research runner：先用于命令行调试，再接 FastAPI。
