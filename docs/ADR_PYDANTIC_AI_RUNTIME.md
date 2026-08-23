# ADR：采用 Pydantic AI 混合运行时

- 状态：Accepted
- 日期：2026-08-23
- 决策范围：v0.2 Agent 基础设施迁移
- 详细执行规范：[Pydantic AI Agent 重构方案](PYDANTIC_AI_MIGRATION.md)

## 背景

项目当前使用自研的 `AgentRuntime`、`LLMToolAgentRuntime`、
`GlobalAgentRuntime` 和 OpenAI-compatible tool loop。它们已经承载证据治理、
预算、审批、trace、run-store 及多个业务工作流，不能通过一次性替换安全迁移。
与此同时，手写工具 schema、provider 分支、结构化输出重试和消息历史适配正在
形成重复基础设施。

## 决策

采用混合架构：Pydantic AI 负责模型/provider 抽象、typed dependency、typed
output、工具调用和消息协议；项目继续负责业务 workflow、证据治理、审批、
run-store、图谱投影和 API 契约。后续只有在合同测试证明等价时，才逐步把
确定性 workflow 迁移到 Pydantic Graph。

迁移由 `AGENT_RUNTIME_MODE` 控制：

- `legacy`：仅执行现有运行时，是默认值和紧急回滚路径；
- `pydantic_ai_shadow`：legacy 结果对外生效，新运行时仅生成对比证据；
- `pydantic_ai_primary`：Pydantic AI 结果对外生效，legacy 在观察期内保留。

所有 provider 必须通过统一 model factory 构造。DeepSeek、SGLang、vLLM 等
OpenAI-compatible endpoint 必须显式设置 provider、base URL、model 和认证，
不得因为缺省配置静默回退到公共 OpenAI endpoint。

## 保持在项目侧的边界

- Evidence、SourceRecord、claim/citation 和 graph provenance；
- AgentBudget、审批策略、scope/risk 权限和写入门禁；
- API request/response、run-store、checkpoint 和幂等语义；
- FinRisk、Supply Chain、generic research 的业务状态机；
- 可审计 trace 和现有工具结果 envelope。

## 非目标

- 不在一个版本内重写全部 Agent；
- 不用自由自治 Agent 替代确定性金融风险流程；
- 不以 Pydantic AI message 对象直接作为长期持久化格式；
- 不在迁移验收前删除 legacy runtime 或改变默认 API 行为。

## 验收与撤销

每个阶段必须满足迁移方案中的测试、shadow、live 和回滚门禁。只有 PAI-7
验收完成并经过观察期，才允许删除 legacy 路径。若新路径出现契约、证据、
预算或稳定性回归，把开关切回 `legacy` 即可恢复已验证路径；持久化 schema
升级必须保持向后读取或提供显式迁移。

## 后果

短期内会同时维护两套运行时并增加 parity 测试成本；作为交换，迁移可按
垂直切片交付、独立回滚，并能用现有 golden fixtures 量化新旧差异。
