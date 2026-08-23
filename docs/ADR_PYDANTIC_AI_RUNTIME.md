# ADR：采用 Pydantic AI 单一 Agent 运行时

- 状态：Accepted，迁移已完成
- 日期：2026-08-23
- 详细记录：[Pydantic AI 迁移完成记录](PYDANTIC_AI_MIGRATION.md)

## 决策

Pydantic AI 是项目唯一的模型驱动 Agent 运行时，负责 provider/model、typed
dependencies、structured output、tools、usage 和消息协议。项目保留业务
workflow、证据治理、预算、审批、run-store、图谱投影和 API 契约。

所有 provider 必须通过 `src.ai.model_factory` 构造。DeepSeek、SGLang、vLLM
等 OpenAI-compatible endpoint 必须显式配置 base URL、model 和认证，不得静默
回退到其他 provider。

## 删除的方案

- `AgentRuntime` 与 `LLMToolAgentRuntime`；
- 自定义 OpenAI tool-call/JSON fallback loop；
- `legacy`、`shadow`、`primary` 运行时选择开关。

`AGENT_RUNTIME_MODE` 已退役且被忽略。旧持久化 run mode 仍可读取，新 run 统一
写入 `pydantic_ai`。

## 保持在项目侧的边界

- Evidence、SourceRecord、claim/citation 和 graph provenance；
- AgentBudget、审批策略、scope/risk 权限和写入门禁；
- API request/response、run-store、checkpoint 和幂等语义；
- FinRisk、Supply Chain、generic research 的业务状态机；
- 可审计 trace 和工具结果 envelope；
- provider 失败后的 cached/fixture/确定性业务降级。

## 部署与回滚

LLM 服务由仓库外部管理，Compose 只启动 Neo4j。新 provider 或版本必须通过离线
回归与 live acceptance。旧运行时删除后，系统性回归通过部署迁移前 Git tag
处理，而不是运行时 feature flag。
