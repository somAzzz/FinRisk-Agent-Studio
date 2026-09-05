# Pydantic AI PAI-1 验收记录

- 验收日期：2026-08-23
- Pydantic AI：`2.33.0`
- Pydantic：`2.12.5`
- 状态：通过

## 已交付

- 显式依赖及可冻结安装的 `uv.lock`；
- SGLang、vLLM、DeepSeek、OpenAI typed provider config；
- 强制显式 endpoint 的统一 model factory；
- DeepSeek 的空值、`EMPTY`、`dummy`、`REPLACE_ME` 等占位凭据在发起网络请求前
  fail fast；
- `AgentDeps`、`AgentPermissions`、`AgentSubject` 和 service boundary；
- `AgentBudget` 到 `UsageLimits` 的映射；
- 使用 `TestModel` 的 typed smoke Agent；
- 测试环境真实模型请求禁用门禁。

## 验证结果

```text
uv lock --check
Resolved 180 packages

pytest tests/ai tests/tools/test_tool_catalog_baseline.py \
  tests/tools/test_tool_contracts.py tests/agents -q
111 passed

pytest -m 'not integration' -q --maxfail=1
987 passed, 1 skipped, 8 deselected in 15.17s
```

全量回归包含 legacy runtime。默认 `AGENT_RUNTIME_MODE` 仍为 `legacy`，因此
本阶段没有接管 `/agent-runs` 或业务 workflow。Pydantic Graph 在同步 smoke test
中产生一条上游 event-loop deprecation warning，不影响执行结果，后续阶段继续
观察并优先使用 async Agent 测试路径。
