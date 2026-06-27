# 07 - Observability, Evaluation, and Local LLM Fallback

## 目标

让 LLM-driven tool loop 可观测、可评估、可在本地模型不支持 native tool calling 时降级。

## Observability

每次 run 必须记录：

- provider。
- model。
- tool loop mode。
- messages。
- requested tool calls。
- executed tool events。
- tool result summaries。
- final answer。
- fallback events。
- token usage。
- latency。

## Trace schema

建议新增：

```text
src/schemas/tool_trace.py
```

包含：

- `ToolExecutionEvent`
- `ToolLoopTrace`
- `ToolBudgetUsage`

## Frontend/API 展示

后续 API 应返回：

```text
GET /workflows/{run_id}/tool-trace
```

Dashboard 展示：

- tool timeline。
- 每轮 LLM request/response。
- tool args。
- tool result summary。
- evidence candidates。
- final answer grounding status。

## Evaluation

新增评估维度：

| 维度 | 问题 |
|---|---|
| tool relevance | LLM 是否选择了合适工具 |
| source quality | search/fetch 来源质量 |
| grounding | final answer 是否被 evidence 支撑 |
| efficiency | 是否过度搜索/fetch |
| safety | 是否请求危险 URL 或 write tool |
| fallback | 本地模型不支持 tool calling 时是否可降级 |

## Golden cases

新增：

```text
tests/fixtures/v20_tool_loop/
```

建议案例：

1. URL 输入应调用 `web_fetch`。
2. “recent/news/latest” 应调用 `web_search` with time_range。
3. “supply chain evidence” 应调用 `search_and_fetch`。
4. filing 查询应调用 `sec_list_filings` 或 `sec_fetch_filing`。
5. transcript 问题应调用 `transcript_lookup`。
6. graph path 问题应调用 `graph_path_search`。

## Local LLM fallback

### Native support detection

提供检测函数：

```python
supports_native_tool_calls(client, model) -> bool
```

可以通过小型 mock-like prompt 低成本检测，或由 config 明确指定。

### Config

```text
LLM_TOOL_MODE=auto
LLM_TOOL_MAX_ROUNDS=4
LLM_TOOL_MAX_RESULT_CHARS=12000
LLM_TOOL_ALLOW_BROWSER=0
```

### JSON fallback

fallback 使用同一个 ToolCatalog 渲染工具列表，不维护单独 prompt 工具定义。

## 测试

新增：

```text
tests/evaluation/test_tool_loop_eval.py
tests/llm/test_tool_loop_fallback.py
```

覆盖：

- tool relevance scoring。
- grounded answer scoring。
- JSON fallback 能执行 mock tool。
- native unsupported 时 auto fallback。
- trace 中标记 fallback mode。

## 验收

```bash
uv run pytest tests/evaluation/test_tool_loop_eval.py tests/llm/test_tool_loop_fallback.py -q
```
