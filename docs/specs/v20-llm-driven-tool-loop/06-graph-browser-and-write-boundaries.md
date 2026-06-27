# 06 - Graph, Browser, and Write Boundaries

## 目标

让 LLM 能使用 graph read 和 browser exploration，但不能越过状态变更边界。

## Graph tools

### graph_query

用途：

- 查询已有实体、公司、风险、证据、关系。
- 读取 graph context。

参数：

```json
{
  "entity": "NVIDIA",
  "relation_types": ["SUPPLIES_TO", "DEPENDS_ON"],
  "max_depth": 2,
  "limit": 20
}
```

后端：

- 使用 `src/graph/queries.py`。
- 必须是参数化 query。
- 不接受 raw Cypher。

### graph_path_search

用途：

- 查找公司与政策、商品、地区、供应商之间的路径。

参数：

```json
{
  "source": "NVIDIA",
  "target": "TSMC",
  "max_paths": 5,
  "max_depth": 3
}
```

输出：

```json
{
  "paths": [
    {
      "nodes": [],
      "edges": [],
      "evidence_ids": [],
      "confidence": 0.72
    }
  ]
}
```

## Browser tool

### browser_explore

用途：

- 当 `web_fetch` 返回 403、动态页面、consent wall 或内容不足时使用。

参数：

```json
{
  "goal": "Find NVIDIA supplier evidence from official or reputable sources",
  "initial_urls": ["https://..."],
  "max_steps": 5
}
```

约束：

- 主 LLM 只能调用 `browser_explore`。
- `browser_explore` 内部可以使用子 agent 控制 click/scroll。
- 子 agent 仍受 SSRF guard、domain blocklist、max steps、timeout 限制。
- 输出必须是 findings，不返回任意 screenshot/base64 给主 LLM，除非用户明确需要。

## Write boundaries

### 不暴露给 LLM 的写操作

- `graph_write`
- `memory_write`
- `report_publish`
- `run_store_update`
- `artifact_write`

### 写入流程

```text
LLM tool result / candidate
    → schema validation
    → evidence binding
    → quality guardrail
    → deterministic writer
```

## Human checkpoint

对于高风险状态变更，可以加入 human checkpoint：

- 新建 graph relation。
- 将 hypothesis 升级为 confirmed。
- 标记 memory item active/rejected。

## 测试

新增：

```text
tests/tools/test_graph_browser_tool_boundaries.py
```

覆盖：

- default catalog 不包含 write tools。
- graph tools 不接受 raw Cypher。
- browser tool 不暴露低层 click/type。
- SSRF blocked URL 返回 safety error。
- graph write 只能由 workflow writer 调用。

## 验收

```bash
uv run pytest tests/tools/test_graph_browser_tool_boundaries.py -q
```
