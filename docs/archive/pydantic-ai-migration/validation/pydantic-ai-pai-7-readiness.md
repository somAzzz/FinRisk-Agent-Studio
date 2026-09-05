# Pydantic AI PAI-7 完成记录

- 日期：2026-08-23
- 状态：通过；默认切换与旧实现删除已完成
- canonical runtime mode：`pydantic_ai`

## 已满足门禁

- API、通用研究、市场研究、filing extraction 和 supply-chain LLM 路径均使用
  Pydantic AI；
- 外部 SGLang `http://127.0.0.1:30000/v1` 对 `qwen3.8-27b` 的真实
  structured-output + local-tool acceptance 通过；
- 旧 `AgentRuntime`、`LLMToolAgentRuntime`、自定义 tool loop 及专用测试删除；
- `AGENT_RUNTIME_MODE` 不再参与运行时选择；
- 新 run 写入 `pydantic_ai`，旧 run mode 仍可反序列化；
- 源码回归门禁阻止旧 runtime 引用重新进入生产目录；
- Compose 不再管理 SGLang/vLLM，只保留 Neo4j。

## Live 结果

| Provider | Model | 结果 | 工具调用 | Requests | Tokens in/out |
| --- | --- | --- | ---: | ---: | ---: |
| SGLang | `qwen3.8-27b` | PASS | 1 | 2 | 1075 / 183 |

## 回滚

旧 runtime 已删除，因此不使用 feature flag 回滚。系统性故障通过部署迁移前版本
恢复；单次 provider 故障继续使用业务级 cached/确定性 fallback，并保留 trace。
