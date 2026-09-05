# Pydantic AI PAI-6 验收记录

- 验收日期：2026-08-23
- 状态：核心持久化与审批合同通过

## 已交付

- `ModelMessagesTypeAdapter` 版本化 message batch；
- memory/SQLite append-only message store；
- operation ID 幂等 append 和冲突 replay 拒绝；
- `POST /agent-runs/{run_id}/resume` 只从服务端恢复 history；每次 resume 新 run ID，
  保留 conversation ID 与 parent run correlation，客户端不能提交伪造 history；
- usage、agent name、run/conversation correlation recorder；
- runtime adapter 成功后自动 recorder 接线；
- memory/SQLite deferred approval 的 approve/deny/expire/cancel/single-use claim；
- SQLite approval 与 audit 跨进程重启可恢复，`BEGIN IMMEDIATE` 事务保证并发
  worker 只有一个能领取已批准调用；
- stream event 内部投影与密钥脱敏；
- 与 legacy SQLite run table 共存和旧记录读取演练。

本阶段没有增加必须部署的 SSE/WebSocket 或 OTel backend；stream projection
已独立于传输层，可在需要时由现有 FastAPI 接口消费。写工具仍不在默认 catalog，
审批历史或客户端 message history 本身不能取得执行权。

## 验证结果

```text
pytest tests/ai/test_message_store.py tests/ai/test_recorder.py \
  tests/ai/test_deferred_tools.py tests/ai/test_stream_events.py \
  tests/ai/test_runtime_adapter.py \
  tests/api/test_agent_runs_api.py tests/api/test_agent_trace_redaction.py \
  tests/api/test_run_store.py -q
30 passed
```

恢复验收同时断言：第二次 adapter 调用接收到第一轮的 request/response history，
而不是只检查 conversation ID 字段相同。
