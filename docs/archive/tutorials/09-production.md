# Chapter 9：当前生产治理、可审计性与验收边界

> 本章区分“仓库已经实现并有测试的能力”和“仍需加固的生产目标”。旧版教程将 Harness
> guardrails、完整 approval authorization、统一 trace adapter 和 release gate 写成同一批待建
> 文件，与当前仓库并不一致。

> 迁移视角：历史 cutover 的分层验收和回滚原则见
> [Runtime Cutover Playbook](migration/runtime/cutover-playbook.md#phase-4用多层证据结束迁移)。

## 本章结果

完成本章后，你应能用现有代码和测试证明：

- schema、Agent validator、领域 quality layer 和人工复核各自负责什么；
- read/interactive/write 工具权限在哪里执行；
- SQLite deferred approval 已保证哪些性质，尚未保证哪些性质；
- memory 为什么不能绕过 evidence 状态与 guardrail；
- 30-case 离线 runner 和 live acceptance 分别能证明什么、不能证明什么。

## 9.1：当前五层防御

| 层 | 当前实现 | 主要职责 |
| --- | --- | --- |
| Pydantic schema | `src/schemas/*`、typed Agent outputs | 类型、范围、额外字段、局部结构 |
| Agent output validator | `src/ai/agents/*` | 单次输出内可判定的不变量与 `ModelRetry` |
| Tool/security policy | `src/ai/toolsets.py`、`src/security/*` | scope/risk、执行复核、URL 安全、脱敏 |
| Deterministic quality | `src/evaluation/*`、workflow quality gate | grounding、source quality、financial safety、context/memory |
| Human review | Agent run state 与 API review endpoints | 候选证据、低置信度、冲突和需人工判断项 |

当前没有采用 Pydantic AI Harness guardrails。不要在实现说明中使用不存在的
`InputGuardrail`、`OutputGuardrail` 或 `ToolGuardrail` 作为证据。

### 规则的唯一主责

| 规则 | 当前主责 |
| --- | --- |
| typed output 禁止额外字段 | Pydantic model |
| 无 evidence 不得标 completed | Agent output validator |
| evidence ID 是否真实存在 | normalizer/quality layer |
| quote/claim grounding | evaluation validator |
| URL 防 SSRF | `src/security/url_guard.py` 与 fetch/browser 边界 |
| 禁止投资建议 | financial-safety evaluation 与 golden cases |
| graph edge 是否可确认 | graph/supply-chain domain layer |
| 工具 scope/risk | visibility filter + execution-time permission check |

防御可以多层重复，但文档必须指出哪个层做最终决定。

## 9.2：当前 deferred approval 实现

`src/ai/approvals.py` 提供 memory 和 SQLite 两种 store，状态为：

```text
pending -> approved -> executed
        -> denied
        -> cancelled
pending/approved -> expired
```

当前已经有测试证明：

- TTL 到期后不可执行；
- denied approval 不可执行；
- decision token 使用 constant-time comparison；
- approved approval 只能领取一次；
- SQLite 重启后仍能恢复；
- `BEGIN IMMEDIATE` 下两个并发 claimant 只有一个成功；
- request/decision/rejection/execution 进入 append-only audit table。

`get_deferred_approval_store()` 与 run/message store 使用相同 SQLite 文件，但独立建表。

### 不能过度宣称的安全保证

当前 approval store 还不是完整的多租户 write authorization 系统：

- `decision_token` 当前作为明文字段持久化，不是 digest；
- 没有保存和校验 arguments digest，审批后参数变化尚无合同保护；
- `principal` 当前主要进入 audit metadata，没有与 `requested_by`/tenant 做强绑定；
- approval store 尚未连接到一个实际的 `write_gated` 工具执行链；
- 没有独立 API authentication/authorization 集成测试覆盖整个 request→approve→execute 流程。

因此当前准确表述是“具备持久化、TTL、原子单次领取和 replay protection 的 deferred approval
存储合同”，不能称为“完整生产级 HITL authorization”。上述缺口适合进入 v0.2 安全加固，不能
靠教程文字当作已完成。

## 9.3：Memory 与 evidence 的当前隔离

当前 memory 是项目自有实现，不是 Harness Memory：

```text
src/memory/models.py
src/memory/store.py
src/memory/ingestion.py
src/memory/context_manager.py
src/memory/rankers.py
src/evaluation/memory_guardrails.py
src/evaluation/context_guardrails.py
```

关键合同：

- web、LLM-extracted 和 hypothesis memory 默认或强制降级为 candidate；
- domain prior 不能冒充 factual evidence；
- confirmed graph edge 必须有证据才能成为 active memory；
- rejected/deprecated memory 不能进入普通 context；
- stale/superseded/hypothesis 即使进入 context 也产生 warning；
- `ContextPack` 按相关性和 token budget 选择，并记录 selected/rejected IDs；
- Global Agent Graph 只把 context pack 当研究上下文，工具输出仍需经过
  `EvidenceCandidateNormalizer`。

这形成：

```text
domain evidence / graph object
  -> adapter
  -> MemoryItem
  -> MemoryWriteGuardrails
  -> candidate / active / blocked
  -> ContextManager
  -> ContextPack
```

它并不意味着长期记忆质量已经生产化。`docs/ROADMAP.md` 明确把相关性、时效性、冲突、撤回、
跨进程恢复和长期校准列为 v0.2 工作。

## 9.4：Trace 与脱敏的真实边界

当前 trace 不是一个总线，而是多个稳定项目合同：

| 来源 | 当前项目类型/位置 |
| --- | --- |
| tool execution | `ToolExecutionEvent` / `ToolLoopTrace` |
| Agent workflow | `AgentRunTrace`、decisions、fallback events |
| FinRisk workflow | `WorkflowTraceEvent` |
| model messages/usage | `StoredMessageBatch` |
| stream event | `InternalAgentStreamEvent` |
| approval | SQLite/in-memory `audit_log` entries |
| memory context | context-pack trace metadata |

`project_stream_event()` 会对 payload 调用 `redact_obj()`；live acceptance CLI 对异常消息调用
`redact_text()`。工具异常会记录类型和摘要，但当前没有统一的 schema-versioned
`trace_adapter.py` 覆盖所有来源。

未来若统一事件合同，必须保持现有 API/run-store 的 backward compatibility，并明确哪些审计写入
失败需要 fail closed，哪些 telemetry 可以降级。

## 9.5：30-case 离线评估的准确含义

`eval/golden_cases.json` 当前有 30 个跨行业和异常场景描述。`eval/run_eval.py`：

- 默认离线执行；
- 所有 case 当前共享同一份 AAPL demo fixture；
- 检查 final status、evidence coverage、financial advice、unsupported claims、schema、source
  diversity 和 hallucination risk；
- 只有 `final_status == "fail"` 返回非零退出码；
- `needs_review` 会报告，但当前不使进程失败。

因此它是稳定的 guardrail/regression matrix，不是 30 家公司的真实数据正确性测试。case 中的
`expected_risk_types` 当前也没有在 runner 中逐项断言。不要据此宣称跨行业金融结论已验证。

真实数据和财务勾稽应分别使用：

- `scripts/real_data_acceptance.py`；
- `scripts/validate_financial_reconciliation.py`；
- `docs/testing/real-data-acceptance.md`；
- `docs/validation/financial-reconciliation.md`。

## 9.6：Live provider acceptance

`scripts/pydantic_ai_live_acceptance.py` 对真实 provider 做一个合成测试：

1. 通过 model factory 解析 provider；
2. 要求模型调用本地 `local_probe(value=7)` 一次；
3. 返回严格的 `LiveAcceptanceOutput`；
4. 检查 tool call 次数；
5. 输出 requests/input/output token usage；
6. 异常类型和脱敏消息进入 JSON，失败返回非零退出码。

该脚本不会发送项目或用户数据。它证明 typed output 和 function calling 的最低兼容性，不证明
金融回答质量，也不直接检查 `/v1/models` health endpoint、validator retry 或所有工具。

示例：

```bash
uv run python scripts/pydantic_ai_live_acceptance.py \
  --provider sglang \
  --base-url http://localhost:30000/v1 \
  --model Qwen/Qwen3.5-35B-A3B
```

401/403 应归类为认证/配置问题；schema 或 tool-call 失败才是模型 capability 问题。

## 9.7：当前发布验证

离线检查：

```bash
uv run python -m pytest -q \
  tests/ai/test_deferred_tools.py \
  tests/ai/test_stream_events.py \
  tests/memory \
  tests/evaluation/test_memory_guardrails.py \
  tests/evaluation/test_context_guardrails.py \
  tests/evaluation/test_release_golden_matrix.py

uv run python eval/run_eval.py
```

provider 可用时再运行 live acceptance。完整发布口径以 `docs/STATUS.md` 和
`docs/ROADMAP.md` 为准，而不是本归档教程。

- [ ] 权限过滤与执行复核均有测试。
- [ ] approval 的已实现保证和待加固项没有混写。
- [ ] memory candidate 不会自动成为 accepted evidence。
- [ ] stream/live 错误输出经过集中脱敏。
- [ ] 知道 30-case runner 共享 fixture 的局限。
- [ ] live acceptance 失败返回非零，并保留安全的错误分类。
- [ ] 没有把 Harness 或不存在的 release-gate 脚本写成当前能力。

## 当前结论

Chapter 9 的治理方向仍然合理，但它不应被实现为一个全新的 `src/ai/governance/` 平行层。
当前仓库已经把多数规则放在领域模型、security、evaluation、memory、toolsets、run store 和 API
边界。后续加固应扩展这些唯一主责模块，并通过 `docs/ROADMAP.md` 管理，而不是再造第二套框架。
