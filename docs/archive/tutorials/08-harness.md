# Chapter 8：Core Runtime 适配、消息恢复与编排取舍

> 当前状态：仓库没有安装或使用 `pydantic-ai-harness`。旧版教程把 Planning、SubAgents、
> ToolOutputLimits 和 DynamicWorkflow 写成待实施迁移，但当前代码和路线图没有采用证据。
> 本章因此改为讲解仓库实际使用的 Pydantic AI Core 边界，以及未来评估 Harness 的门槛。

## 本章结果

完成本章后，你应能解释：

- Pydantic AI Agent 如何接入现有同步 workflow；
- message batch 怎样幂等保存并恢复为框架消息；
- run identity 与 conversation identity 为什么不能混为一谈；
- 当前项目为什么选择 Core Agent + Pydantic Graph，而没有再引入 Harness；
- 什么证据足以支持未来增加新的 orchestration capability。

## 版本与事实基线

当前 `uv.lock` 安装：

```text
pydantic-ai       2.27.1
pydantic-ai-slim  2.27.1
pydantic-ai-harness 未安装
```

`pyproject.toml` 使用 `pydantic-ai>=2.0.0,<3.0.0`，没有 `harness` dependency group。不要运行
旧教程中的 `uv run --group harness ...`，也不要创建一个没有调用方的 `src/ai/harness/` 目录。

## 当前文件地图

| 文件 | 当前职责 |
| --- | --- |
| `src/ai/runtime_adapter.py` | Agent 的同步 workflow adapter、history、usage 和 tool trace 投影 |
| `src/ai/runtime_types.py` | `LLMToolRunResult` 与 `LLMToolCallRecord` |
| `src/ai/message_store.py` | versioned message batch、memory/SQLite store、框架消息编解码 |
| `src/ai/recorder.py` | 只追加本次 run 的 new messages 和 usage |
| `src/ai/store_factory.py` | 根据 `RUN_STORE_BACKEND` 选择 memory 或 SQLite |
| `src/ai/stream_events.py` | 把框架 stream event 投影为脱敏的项目内部事件 |
| `src/ai/graphs/parallel_policy.py` | 在启用并行前检查 state read/write 冲突 |
| `src/api/agent_runs.py` | composition root：model、catalog、deps、planner、runtime 和 recorder |

## 8.1：同步业务边界接入 async Agent

当前 workflow 和 API 的部分核心合同仍是同步调用，例如 `SubgoalRuntime.run(goal)`。真正的模型
调用则是异步 `Agent.run()`。`run_awaitable_sync()` 处理两种场景：

```text
当前线程没有 event loop -> asyncio.run(awaitable)
当前线程已有 event loop -> 新线程内 asyncio.run(awaitable)，join 后传播结果/异常
```

这避免在运行中的 loop 内再次调用 `asyncio.run()`。它也有明确成本：调用线程会等待，取消和
context propagation 比全 async 调用链更弱。因此应把它限制在 adapter 边界，不应散落到工具和
领域模块。

练习时追踪以下路径：

```text
src/api/agent_runs.py::_build_pydantic_agent_runtime
  -> PydanticAIPlanner
  -> GlobalAgentRuntime
  -> Global Agent Graph
  -> PydanticAIRuntimeAdapter.run
  -> Agent.run
```

## 8.2：run 与 conversation 是两个 identity

当前约定：

- `run_id` 标识一次具体执行；
- `conversation_id` 把多次执行关联为可恢复对话；
- resume 创建新 run ID，但沿用可信的 conversation ID；
- prompt 不能自行指定或覆盖别的 conversation history。

`PydanticAIRuntimeAdapter._run_and_record()` 只有在
`deps.load_message_history=True` 且注入 recorder 时才加载历史。随后它把 history 传给
`Agent.run()`，成功后只记录 `result.new_messages()`。

这一设计避免每次续跑重复保存全部历史，也避免客户端提交一段伪造的模型消息冒充服务端历史。

## 8.3：versioned、append-only message batches

`StoredMessageBatch` 的关键字段是：

```text
schema_version
operation_id
conversation_id
run_id
agent_name
messages[]
usage{}
created_at
```

`operation_id = f"{run_id}:{agent_name}"` 是幂等键：

- 相同 operation、相同语义内容再次 append 返回 `False`；
- 相同 operation、不同内容抛出 `MessageReplayError`；
- `created_at` 不参与语义相等比较；
- `ModelMessagesTypeAdapter` 负责框架消息的序列化与恢复，不能用任意 dict 手工猜消息结构。

SQLite store 新建独立 `agent_message_batches` 表，不修改既有 run tables。测试明确证明旧
`FinRiskSQLiteRunStore` 数据在增加 message table 后仍可读取。

## 8.4：Store factory 与持久化范围

`get_agent_message_store()` 和 `get_deferred_approval_store()` 共用：

```text
RUN_STORE_BACKEND=memory | sqlite
RUN_STORE_DB=.cache/finrisk_agent_studio/runs.sqlite3
```

memory 适合测试和 demo；SQLite 支持进程重启后的 message/approval 恢复。工厂使用
`lru_cache` 提供进程内单例，测试通过 `reset_agent_message_store_for_tests()` 清理工厂缓存。

不要把这个工厂误解为全局 Agent deps：run-specific permissions、subject、budget 和 identity
仍需每次构造。

## 8.5：框架事件不是直接的 API contract

`project_stream_event()` 接受 dataclass、Pydantic model 或普通框架对象，投影为：

```text
event_id
sequence
event_type
payload
created_at
```

payload 会经过 `src.security.redaction.redact_obj()`。API 不应直接序列化未知 Pydantic AI 内部
对象，因为框架升级可能改变字段，也可能意外包含 secret。

当前这是一个轻量 stream projection，不是覆盖 model、tool、Graph、approval、memory 的统一
事件总线。旧版教程中所述完整 `trace_adapter.py` 尚不存在。

## 8.6：当前上下文与结果大小策略

当前没有 Harness `ToolOutputLimits`。工具结果限制分为：

1. `ProjectTool.max_result_chars`：单次工具返回进入 envelope 前截断；
2. `AgentBudget.max_total_tool_result_chars`：runtime 结果中用于记录总预算口径；
3. browser summary 输入：最多取页面内容前 5000 字符；
4. memory context：由 `ContextManager` 的 token budget 选择。

这里尚没有通用 spill/summarize store。不要在教程中宣称超长原始 payload 已自动持久化并可分页
读取；如未来实现，应先区分原始 evidence retention 与模型 context copy。

## 8.7：为什么当前不采用 Harness

当前 Core 已覆盖 v0.1 必需能力：

- typed output 和 output validator；
- typed tools 与权限过滤；
- Pydantic Graph 状态机；
- message history/resume；
- usage limits；
- project-owned trace、approval、memory 和 quality gate。

增加 Harness 会引入另一组 planning/delegation/store/trace 语义。目前没有固定 fixtures 对比报告
证明它能降低遗漏、重复调用、token 或延迟，也没有路线图工作包要求它。因此“不采用”是当前
合理选择，不是能力缺失。

未来只有在以下条件满足时才重新评估：

- 使用同一组 fake tools 和预算比较 Core 与候选 capability；
- unsupported claim 和 permission violation 不恶化；
- child usage、failure 和 trace 可归集到 parent run；
- 不替换 deterministic workflow、quality gate 或 authorization；
- 精确锁定并验证实际安装版本；
- 有删除或简化现有代码的明确收益，而非只增加抽象层。

## 8.8：测试与验收

```bash
uv run python -m pytest -q \
  tests/ai/test_runtime_adapter.py \
  tests/ai/test_message_store.py \
  tests/ai/test_recorder.py \
  tests/ai/test_stream_events.py \
  tests/ai/graphs/test_parallel_policy.py \
  tests/api/test_agent_runs_api.py
```

确认依赖事实：

```bash
uv run python -c \
  "import importlib.metadata as m; print(m.version('pydantic-ai'))"
rg -n "pydantic-ai-harness|src/ai/harness" pyproject.toml uv.lock src tests
```

第二条当前应无生产命中。

- [ ] resume 使用新 run ID 和旧 conversation ID。
- [ ] message append 幂等，冲突 replay 明确失败。
- [ ] SQLite message table 不破坏旧 run data。
- [ ] stream payload 在暴露前经过集中脱敏。
- [ ] adapter 没有实现第二套模型 loop。
- [ ] 没有把未采用的 Harness capability 写成当前功能。

下一章在这些真实边界之上检查权限、审批、memory、离线评估和 live provider 验收。
