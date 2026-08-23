# Pydantic AI PAI-7 切换准备记录

- 检查日期：2026-08-23
- 状态：未获准默认切换；legacy 删除门禁未满足

## 已准备

- `/agent-runs` 在 `pydantic_ai_primary` 下使用 typed toolset 和
  `PydanticAIRuntimeAdapter`，planner 也使用 typed output；
- filing risk 与 supplier relation 的 primary 解析已切到 typed Agent client；
- API resume 使用服务端 message store，SQLite approval claim 具备事务级并发保护；
- 每个 Agent run 持久化实际 `runtime_mode`，旧记录缺省为 `legacy`；
- `pydantic_ai_live_acceptance.py` 提供合成 typed-output + local-tool live 合同；
- `pydantic_ai_observation_gate.py` 将 primary 数量、观察时长、失败和 fallback-zero
  转成机器可判定报告；
- `legacy`、`pydantic_ai_shadow`、`pydantic_ai_primary` 均有配置合同；
- import-all、demo CLI、API/trace/review、cached fixtures 和全量非集成测试通过；
- 变更范围 Ruff、lockfile 和 whitespace 门禁通过；
- emergency rollback 仍为 `AGENT_RUNTIME_MODE=legacy`。

## 暂不切默认值的原因

本地 SGLang `127.0.0.1:30000` 与 vLLM `127.0.0.1:8000` 均未监听。一次经批准的
最小 DeepSeek typed-output + local-tool live 验收到达服务端，但占位凭据
`REPLACE_ME` 被返回 401；model factory 已补充本地 fail-fast，后续不会再把已知
占位符发送到公网。当前仍没有有效 live provider，也没有一个发布周期的 primary
观测数据。迁移方案明确要求 live acceptance、连续稳定运行和 fallback 使用量
归零后才能切默认并删除旧实现，因此默认保持 `legacy`。

## Provider 门禁矩阵

| Provider | 本次结果 | 下一步 |
| --- | --- | --- |
| TestModel/FunctionModel | typed output、tool、history continuation 通过 | 继续作为 CI 门禁 |
| SGLang | `127.0.0.1:30000` connection refused | 启动兼容服务后跑 live 合同 |
| vLLM | `127.0.0.1:8000` connection refused | 启动兼容服务后跑 live 合同 |
| DeepSeek | endpoint 可达，401 invalid placeholder | 配置有效密钥后重跑最小 live 合同 |

完整命令、退出码、默认切换检查表和回滚步骤见
[Pydantic AI 切流与回滚 Runbook](../guides/pydantic-ai-cutover.md)。

## Legacy 引用盘点

以下生产引用仍存在，因此不满足删除准入条件：

- `src/pipelines/llm_tool_research.py` → `LLMToolAgentRuntime`；
- `src/llm/client.py` → `OpenAICompatibleToolLoop`、
  `JSONToolChoiceToolLoop`；
- `src/llm/deepseek_client.py` → `OpenAICompatibleToolLoop`；
- `src/supply_chain/steps/supplier_discovery.py` → legacy runtime fallback；
- `src/workflows/steps/market_explorer_step.py` → legacy shadow/rollback；
- `src/agents/__init__.py` → legacy public compatibility exports；
- typed toolset 在迁移观察期继续复用 `ProjectTool` callable 与治理 metadata。

这些引用是有文档的 emergency/shadow 路径，不是未发现的残留。删除需在部署
环境完成 live provider matrix、观察一个发布周期、建立迁移前 tag/commit 后进行。

## 当前发布门禁结果

```text
pytest -m 'not integration' -q --maxfail=1
1036 passed, 1 skipped, 8 deselected in 16.06s

pytest tests/test_import_all_modules.py -q
1 passed

python -m src.workflows.finrisk_workflow ... --demo-mode
status: completed; completed steps: 9; final_status: pass
```
