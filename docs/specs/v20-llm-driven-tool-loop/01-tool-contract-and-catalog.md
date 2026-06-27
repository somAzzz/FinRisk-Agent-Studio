# 01 - Tool Contract and Catalog

## 目标

把当前 `src/tools/catalog.py` 从“手写 schema + function map”升级为全项目统一工具契约。

每个 LLM-visible tool 必须同时定义：

- OpenAI-compatible schema。
- Python executable。
- 输入 Pydantic schema。
- 输出 serializer。
- risk level。
- budget policy。
- evidence conversion hint。
- workflow/tool visibility scope。

## 核心对象

建议新增或扩展：

```text
src/tools/catalog.py
src/tools/contracts.py
```

### ProjectTool

```python
class ProjectTool(BaseModel):
    name: str
    description: str
    parameters: dict
    callable: Callable[..., Any]
    risk_level: Literal["read_only", "interactive", "write_gated"]
    scopes: set[str]
    max_result_chars: int = 12000
    evidence_kind: Literal[
        "web",
        "filing",
        "transcript",
        "financial_metric",
        "graph_path",
        "browser",
        "none",
    ]
```

`ProjectTool` 不一定直接是 Pydantic model，因为 callable 不能自然序列化；可以用 dataclass + Pydantic input/output models。

### ToolCatalog

必须支持：

```python
catalog = build_project_tool_catalog()
catalog.for_scope("finrisk_market")
catalog.for_scope("supply_chain")
catalog.select(["web_search", "web_fetch"])
catalog.openai_tools
catalog.tool_map
```

## OpenAI-compatible schema 规范

所有工具必须输出：

```json
{
  "type": "function",
  "function": {
    "name": "...",
    "description": "...",
    "parameters": {
      "type": "object",
      "properties": {},
      "required": []
    }
  }
}
```

禁止混用 Anthropic 风格：

```json
{"name": "...", "input_schema": {...}}
```

如果后续需要 Anthropic/Gemini，必须由 adapter 从同一个 ProjectTool 转换，不能维护第二套定义。

## 工具分类

### read_only

可以直接由 LLM 调用：

- `web_search`
- `web_fetch`
- `search_and_fetch`
- `sec_list_filings`
- `sec_fetch_filing`
- `transcript_lookup`
- `financial_metrics_lookup`
- `xbrl_fact_lookup`
- `graph_query`
- `graph_path_search`

### interactive

只能作为高级子 agent 调用：

- `browser_explore`

不暴露：

- `browser_click`
- `browser_type`
- `browser_scroll`

### write_gated

不直接暴露给 LLM，只能由 workflow 在 guardrail 通过后执行：

- `graph_write`
- `memory_write`
- `report_publish`
- `run_store_update`

## 输出规范

所有工具输出必须 JSON-serializable。

建议 envelope：

```json
{
  "tool": "web_search",
  "status": "success",
  "retrieved_at": "...",
  "data": {},
  "evidence_candidates": [],
  "warnings": [],
  "truncated": false
}
```

第一阶段可继续返回现有 provider response 的 JSON dump，但进入 workflow 前必须能转换为 evidence。

## 安全要求

- ToolCatalog 不得包含 API key。
- schema description 不得暴露内部 secret 路径。
- 每个 URL 工具必须复用 SSRF guard。
- 每个工具必须有 max result size。
- unknown tool 必须返回 tool error，不执行任何 fallback。

## 测试

新增：

```text
tests/tools/test_tool_contracts.py
```

覆盖：

- 所有 tools 都是 OpenAI-compatible schema。
- 每个 schema name 在 tool_map 中存在。
- 每个 tool_map callable 输出 JSON-serializable。
- select/scope 不会返回未授权工具。
- write_gated tools 不出现在默认 LLM catalog。

## 验收

```bash
uv run pytest tests/tools/test_tool_catalog.py tests/tools/test_tool_contracts.py -q
uv run ruff check src/tools tests/tools
```
