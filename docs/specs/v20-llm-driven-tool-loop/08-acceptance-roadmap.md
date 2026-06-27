# 08 - Acceptance Roadmap

## 分步落地顺序

### Milestone 1 - Tool Contract Foundation

实现：

- `ProjectTool` / contracts。
- ToolCatalog scopes。
- tool output envelope。
- write-gated tools 排除默认 catalog。

验收：

```bash
uv run pytest tests/tools/test_tool_contracts.py tests/tools/test_tool_catalog.py -q
```

### Milestone 2 - Data Tools

实现：

- `sec_list_filings`
- `sec_fetch_filing`
- `transcript_lookup`
- `financial_metrics_lookup`
- `xbrl_fact_lookup`

验收：

```bash
uv run pytest tests/tools/test_data_tool_catalog.py -q
```

### Milestone 3 - Tool Loop Observability

实现：

- `ToolExecutionEvent`
- `ToolLoopTrace`
- tool result budget / truncation。
- API-ready trace serialization。

验收：

```bash
uv run pytest tests/llm/test_tool_loop.py tests/agents/test_llm_runtime.py -q
```

### Milestone 4 - FinRisk Shadow Migration

实现：

- `MarketExplorerStep` shadow mode。
- LLM tool run trace。
- Evidence candidates but not primary report input。

验收：

```bash
uv run pytest tests/workflows/test_llm_market_explorer_step.py -q
```

### Milestone 5 - FinRisk Primary Migration

实现：

- LLM-driven market explorer primary mode。
- deterministic fallback。
- source quality / grounding gate。

验收：

```bash
uv run pytest tests/workflows tests/evaluation -q
```

### Milestone 6 - Supply Chain Migration

实现：

- LLM query generation。
- LLM tool loop discovery。
- SupplierCandidate validation。
- evidence-gated edge write。

验收：

```bash
uv run pytest tests/supply_chain/test_llm_supplier_discovery.py tests/supply_chain -q
```

### Milestone 7 - Graph and Browser Tools

实现：

- `graph_query`
- `graph_path_search`
- `browser_explore`
- no raw Cypher / no low-level browser actions。

验收：

```bash
uv run pytest tests/tools/test_graph_browser_tool_boundaries.py -q
```

### Milestone 8 - Local LLM Fallback

实现：

- native/fallback/auto mode。
- JSON ToolChoice fallback。
- model capability config。

验收：

```bash
uv run pytest tests/llm/test_tool_loop_fallback.py -q
```

### Milestone 9 - Real Case Runner

实现：

```text
src/pipelines/llm_tool_research.py
```

支持：

- `--provider deepseek`
- `--provider vllm`
- `--provider sglang`
- `--tools company_research|finrisk_market|supply_chain`
- `--max-tool-rounds`
- `--json-trace-output`

验收：

```bash
uv run python -m src.pipelines.llm_tool_research \
  --provider deepseek \
  --query "Find evidence about Apple's supply chain risk."
```

必须输出：

- final answer。
- tool calls list。
- evidence/source URLs。
- uncertainty。
- trace path。

## Done Definition

V20 完成时，系统应满足：

1. DeepSeek 和本地 LLM 共用同一套 ToolCatalog。
2. LLM 能选择不止 web search 的工具。
3. SEC、transcript、financial metrics、graph read 至少有 mock-backed tool tests。
4. FinRisk workflow 至少一个 real-mode step 使用 LLM-driven tool loop。
5. Supply Chain workflow 至少 supplier discovery 支持 LLM-driven shadow mode。
6. write tools 不在 default LLM catalog。
7. 全量测试通过。

## 推荐提交拆分

1. `add project tool contracts`
2. `add sec transcript financial llm tools`
3. `add tool loop trace events`
4. `add llm market explorer shadow mode`
5. `migrate market explorer to llm tool loop`
6. `add llm supplier discovery shadow mode`
7. `add graph browser read-only tools`
8. `add local llm json tool fallback`
9. `add llm tool research runner`
