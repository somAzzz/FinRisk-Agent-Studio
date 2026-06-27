# 02 - Provider-neutral Tool Loop Runtime

## 目标

把 `OpenAICompatibleToolLoop` 作为所有 provider 的标准工具调用内核。

适用 provider：

- DeepSeek public API。
- Local vLLM。
- Local SGLang。
- OpenAI-compatible hosted endpoint。

## 当前状态

已完成：

- `src/llm/tool_loop.py`
- `DeepSeekClient.complete_with_tools`
- `DeepSeekClient.chat_with_tools`
- `EdgarLLMClient.complete_with_tools`
- `EdgarLLMClient.chat_with_tools`
- `src/agents/llm_runtime.py`

## 下一步增强

### Tool result budget

新增参数：

```python
max_tool_result_chars: int = 12000
max_total_tool_result_chars: int = 40000
```

当工具结果过长：

- 优先保留 metadata、url、title、quote/snippet。
- content 截断并标记 `truncated=true`。
- 不让单个网页正文撑爆上下文。

### Tool execution events

新增 trace object：

```python
class ToolExecutionEvent(BaseModel):
    event_id: str
    round_id: str
    tool_call_id: str
    tool_name: str
    arguments: dict
    status: Literal["success", "failed"]
    result_summary: str
    latency_ms: int
    error: str | None
```

`LLMCall` 记录 model side，`ToolExecutionEvent` 记录 backend side。

### Native / fallback mode

新增：

```python
ToolLoopMode = Literal["native", "json_fallback", "auto"]
```

- `native`：发送 OpenAI-compatible `tools`。
- `json_fallback`：让模型输出 JSON `ToolChoice`。
- `auto`：native 失败时降级，但必须在 trace 中标记。

## JSON fallback 协议

当 local model/server 不支持 `tools` 时，使用同一 catalog 生成 prompt：

```json
{
  "thought": "...",
  "tool": "web_search",
  "arguments": {"query": "..."},
  "finish": false,
  "answer": null
}
```

后端校验：

- `tool` 必须存在于 ToolCatalog。
- `arguments` 必须通过 Pydantic/schema 校验。
- `finish=true` 时不得同时请求工具。

## Runtime API

`LLMToolAgentRuntime.run(goal)` 当前返回：

- final answer。
- tool call records。
- llm calls。

后续应返回：

- tool execution events。
- context/evidence candidates。
- fallback mode。
- provider/model metadata。

建议：

```python
class LLMToolRunResult(BaseModel):
    goal: str
    final_answer: str
    tool_calls: list[LLMToolCallRecord]
    tool_events: list[ToolExecutionEvent]
    llm_calls: list[LLMCall]
    evidence_candidates: list[Evidence]
    mode: ToolLoopMode
```

## 错误处理

工具错误不应直接中断 loop，除非是安全错误。

| 错误 | 行为 |
|---|---|
| unknown tool | 返回 role=tool error |
| invalid JSON args | 返回 role=tool error |
| schema validation error | 返回 role=tool error |
| tool exception | 返回 role=tool error |
| SSRF blocked | 返回 role=tool safety error |
| max rounds exceeded | runtime error |
| provider auth failure | runtime error |

## 测试

扩展：

```text
tests/llm/test_tool_loop.py
tests/agents/test_llm_runtime.py
```

新增覆盖：

- tool result truncation。
- backend ToolExecutionEvent。
- JSON fallback mode。
- native failure auto fallback。
- max rounds 触发后保留完整 trace。

## 验收

```bash
uv run pytest tests/llm/test_tool_loop.py tests/agents/test_llm_runtime.py -q
```
