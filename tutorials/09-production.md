# Chapter 9：生产治理与迁移评估

## 学习目标

把 schema、Agent validator、Harness guardrail、FinRisk quality layer 和 human review 组织为互补的防御体系，并保持 memory、审批、trace 和评估的领域边界。

## 五层防御

```text
1. Pydantic schema
   -> 结构正确

2. Agent output validator
   -> 单次输出的可确定业务约束

3. Harness input/tool/output guardrails
   -> Agent runtime 的阻止、替换、重试或脱敏

4. FinRisk deterministic quality layer
   -> 跨步骤 evidence、claim、source、graph、financial safety

5. Human review
   -> 高风险、写操作、低置信度和冲突结果
```

上层不能因为下层存在而被删除。例如 schema 正确不代表 claim 有证据，Harness output guardrail 也不能替代跨步骤 grounding。

## 练习 9.1：Guardrail 分层表

为这些规则选择唯一主责层，并写出其他层如何补充：

- 禁止额外 JSON 字段；
- finding 必须有 evidence ID；
- evidence ID 必须存在；
- quote 必须支持 claim；
- 禁止直接投资建议；
- URL 必须通过 SSRF guard；
- 写工具必须审批；
- 高置信度但证据不足需降级；
- source diversity 不足需 review；
- graph edge 必须存在。

若同一规则在多层重复，说明是 defense in depth 还是不必要重复。

## 练习 9.2：Harness guardrail lab

在隔离 Agent 上实现一个“不输出投资建议”的 output guardrail，测试：

- 正常研究结论 allow；
- 明确 buy/sell 指令 block；
- 大小写和简单变体；
- 误报样例，例如引用公司评级但不是向用户建议；
- blocked verdict 进入项目 trace；
- guardrail failure 不被标成 provider failure。

关键词列表只能作为第一版实验。生产规则需要评估误报/漏报，并与已有 `financial_safety_validator` 协同。

## 练习 9.3：HITL 不等于 authorization

当前 `src/ai/approvals.py` 已实现服务端审批状态、过期、single-use claim 和 replay protection。设计 Harness deferred approval 到该 store 的适配合同，但不要绕开：

- API authentication；
- principal/tenant authorization；
- tool scope 与 risk level；
- TTL；
- reviewer identity；
- decision token；
- 原子 claim；
- audit log；
- restart-safe persistence。

测试必须覆盖 approve、deny、expire、cancel、wrong token 和 replay。

## 练习 9.4：两种 Memory

建立严格分类：

| Harness Agent memory | FinRisk domain memory/evidence |
| --- | --- |
| 调研笔记 | 经过验证的 evidence |
| 偏好的研究策略 | claim/evidence binding |
| 未解决问题 | provenance 与 trust state |
| 跨 session 提醒 | lifecycle 与审计记录 |
| 可被模型写入 | 只能经 domain policy 接纳 |

核心不变量：模型写入 memory 的“TSMC supplies X”不能在下一次运行自动成为 confirmed fact。

设计 promotion flow：Agent note → evidence candidate → source fetch/validation → accepted evidence → claim。任何跳步都应失败或 needs_review。

## 练习 9.5：Trace adapter

保持现有 frontend/API trace contract。设计 mapping：

| Pydantic/Harness event | FinRisk event |
| --- | --- |
| model request/response | `LLMCall` / message record |
| tool call/result | `ToolExecutionEvent` |
| delegation | subgoal/agent trace |
| planning update | plan trace，不是 evidence |
| guardrail verdict | quality/guardrail finding |
| approval request/decision | approval audit event |
| memory read/write | redacted memory trace |
| usage | request/tool/token/cost budget usage |

要求：run ID、conversation ID、subgoal ID、tool call ID 可关联；敏感 prompt、API key 和隐私文本按现有 security policy 脱敏。

## 练习 9.6：最终评估集

建议目录：

```text
eval/migration/
  cases.yaml
  run_core.py
  run_harness.py
  compare.py
```

至少 30 个 case：

| 类型 | 数量 |
| --- | ---: |
| company risk | 10 |
| current market | 5 |
| supply chain / graph | 5 |
| ambiguous | 5 |
| missing evidence | 5 |

Core 与 Harness 必须使用相同 case、fixtures、tool responses 和 domain validators。比较：

- tool selection accuracy；
- evidence coverage；
- unsupported claim rate；
- source diversity；
- human-review precision/recall；
- tool calls、requests、tokens、latency；
- deterministic score parity；
- trace completeness；
- approval policy parity。

最重要 gate：unsupported claim rate 不得恶化。回答更长、计划更漂亮或调用更多 Agent 都不是成功标准。

## 练习 9.7：发布与回滚说明

如果最终决定把 Harness 接入生产，先写 ADR：

- 具体采用哪些 capabilities；
- 哪些当前组件保持不变；
- 为什么不采用其他 capabilities；
- 版本 pin 和升级策略；
- migration/cutover 方式；
- rollback 是部署前 tag，而不是恢复已删除 legacy runtime；
- live acceptance 与离线 gate；
- API/trace compatibility。

## DoD

- [ ] 五层防御职责清楚且有测试。
- [ ] Harness guardrail 不替代 FinRisk quality layer。
- [ ] 写操作审批保留服务端授权、TTL 与 replay protection。
- [ ] Agent memory 与 evidence store 严格分离。
- [ ] Harness event 能适配现有 trace contract。
- [ ] 30-case Core vs Harness eval 可重复。
- [ ] unsupported claim rate 不恶化。
- [ ] deterministic score parity 保持。
- [ ] 发布与回滚 ADR 已完成。

## 最终知识检查

完成十章后，你应能清楚解释这条演进：

```text
OpenAI-compatible SDK
  -> typed Pydantic AI Agent
  -> dependencies + toolsets
  -> structured specialist agents
  -> programmatic workflow / delegation
  -> selected Harness capabilities
  -> layered production guardrails
  -> memory separation + HITL + observability + evals
```

最成熟的结论不是“我把所有代码变成 Agent”，而是：我能说明每一个模型边界为何存在、每一个确定性规则为何保留，以及系统如何证明输出有证据、受权限控制并可审计。

