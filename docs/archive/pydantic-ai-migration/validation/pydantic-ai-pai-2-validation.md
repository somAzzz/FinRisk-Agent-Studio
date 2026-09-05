# Pydantic AI PAI-2 验收记录

- 验收日期：2026-08-23
- 状态：通过

## 已交付

- 13 个项目工具的 typed Python signature 与 Pydantic schema；
- company research、market、supply-chain 等 scope 的动态过滤；
- interactive/write-gated 的模型可见性和执行时双重权限检查；
- legacy callable、结果截断和稳定 envelope 的复用；
- `ToolExecutionEvent` 事件投影；
- 满足现有 `SubgoalRuntime` 的 `PydanticAIRuntimeAdapter`。

Legacy `ProjectTool` 和自研 tool loop 均未删除；`AGENT_RUNTIME_MODE=legacy`
仍是默认回滚路径。

## 验证结果

```text
pytest tests/ai/test_toolsets.py tests/ai/test_runtime_adapter.py \
  tests/tools/test_tool_catalog.py tests/tools/test_tool_contracts.py \
  tests/tools/test_data_tool_catalog.py \
  tests/tools/test_graph_browser_tool_boundaries.py \
  tests/agents/test_global_agent_runtime.py -q
38 passed

pytest -m 'not integration' -q --maxfail=1
993 passed, 1 skipped, 8 deselected in 15.94s
```

Typed schema parity gate覆盖工具名、参数集合、required 字段及 scope/risk/evidence/
result-limit metadata。参数默认值以实际 Python callable 语义为准；legacy 手写
schema snapshot 继续保留，用于识别任何有意的模型可见契约差异。
