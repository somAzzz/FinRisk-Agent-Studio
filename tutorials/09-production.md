# Chapter 9：生产治理、可审计性与迁移验收

## 本章结果

本章把 typed schema、Agent validators、Harness guardrails、领域 quality layer 和 human
review 组织成职责清楚的防御体系；同时完成服务端审批、memory/evidence 隔离、统一 trace、
可重复 eval、live acceptance 和发布/回滚 ADR。

完成本章不代表“模型不会犯错”，而是系统能阻止越权、识别证据不足、保留审计记录，
并用同一数据集证明新架构没有让核心质量退化。

前置条件：Chapter 8 已产出 Core/Harness 对比报告，并明确 production profile 采用和
拒绝哪些 capabilities；未通过 gate 的 capability 不得带入本章。

## 文件变更总览

### 新建治理代码

| 文件 | 必须实现的职责 | 替代的旧做法 |
| --- | --- | --- |
| `src/ai/governance/__init__.py` | 导出稳定治理边界 | 防止业务模块直接依赖 Harness 内部类型 |
| `src/ai/governance/guardrails.py` | 构建 input/output/tool guardrails，映射 verdict | 替代 prompt 中“请勿……”式软约束和散落关键词检查 |
| `src/ai/governance/approvals.py` | approval model、store protocol、SQLite 实现、TTL/replay | 替代进程内 bool 或把模型确认当授权 |
| `src/ai/governance/deferred_tools.py` | Pydantic deferred call 与服务端 approval store 的适配 | 替代 tool 内临时询问后直接执行 |
| `src/ai/governance/memory_policy.py` | memory namespace、读取/写入 policy、promotion contract | 阻止 model-written note 自动成为 evidence |
| `src/ai/governance/trace_adapter.py` | 将 Core/Harness/Graph 事件映射为项目 trace | 替代互不关联的日志和不稳定框架对象直出 API |

### 新建评估与运维文件

```text
eval/migration/
  README.md
  cases.json
  models.py
  evaluators.py
  run_core.py
  run_harness.py
  compare.py
scripts/
  pydantic_ai_live_acceptance.py
  pydantic_ai_release_gate.py
docs/adr/
  00XX-pydantic-ai-harness-production-profile.md
docs/operations/
  pydantic-ai-runbook.md
```

| 文件 | 职责 |
| --- | --- |
| `cases.json` | 至少 30 个版本化 case；输入、fixtures、expected invariants |
| `models.py` | eval case/result/report 的 typed schema |
| `evaluators.py` | 纯函数或可重复 evaluator；不混入 runner |
| `run_core.py` | 使用 Chapter 7 Core baseline 运行同一数据集 |
| `run_harness.py` | 使用 Chapter 8 production profile 运行同一数据集 |
| `compare.py` | 生成 machine-readable diff，并按 gate 返回非零 exit code |
| live acceptance | 对真实 provider 验证 typed output、tool call、usage、trace |
| release gate | 汇总 unit/eval/live 结果；任一关键 gate 失败即阻止发布 |
| ADR | 记录采用/拒绝的 capability、版本、风险、cutover 与 rollback |
| runbook | provider、store、approval、spill、trace 故障的诊断步骤 |

### 新建测试

```text
tests/ai/governance/
  __init__.py
  test_guardrails.py
  test_approvals.py
  test_deferred_tools.py
  test_memory_policy.py
  test_trace_adapter.py
tests/security/
  test_redaction.py
tests/eval/
  test_migration_models.py
  test_migration_evaluators.py
  test_migration_compare.py
tests/scripts/
  test_pydantic_ai_release_gate.py
```

### 修改文件

| 文件 | 修改内容 | 限制 |
| --- | --- | --- |
| `src/api/agent_runs.py` | 从认证 principal 构造 permissions；暴露稳定 trace/approval API | 不接收客户端自报 `allow_write` |
| `src/agents/state.py` | 增加 guardrail、approval、memory、delegation correlation state | 不存 secret/raw private prompt |
| `src/ai/run_service.py` | 统一记录 guardrail verdict、usage、终态 | guardrail failure 不标成 provider failure |
| `src/security/url_guard.py`、`src/security/redaction.py` | 作为唯一 domain security policy 被新治理层调用并补齐测试 | Harness guardrail 不复制/取代 SSRF 与脱敏 policy |
| `pyproject.toml`、`uv.lock` | 如使用 Pydantic Evals，精确锁定与 Core 相容版本 | eval 依赖可放独立 group |

本章不重新引入 Chapter 7 删除的任何文件。临时 migration/shadow flag 或一次性比较脚本若
不再被 release gate 使用，应在本章结束时删除。

## 9.1：五层防御与唯一主责

```text
1. Pydantic schema
   结构、类型、范围、额外字段

2. Agent output validator
   单次输出内可确定的业务不变量与有界 retry

3. Harness input/output/tool guardrails
   run 边界的 allow / replace / retry / block

4. FinRisk deterministic quality layer
   跨步骤 evidence、claim、source、graph、financial safety

5. Human review
   写操作、高风险、冲突、低证据、政策例外
```

在 `guardrails.py` 的模块文档中为每条规则指定唯一主责层：

| 规则 | 主责层 | 其他层的作用 |
| --- | --- | --- |
| 禁止额外 JSON 字段 | schema | 测试防回归 |
| finding 必须有 evidence ID | output model/validator | quality layer 验证 ID 真实存在 |
| quote 支持 claim | quality layer | human review 处理边界样例 |
| URL 防 SSRF | security/tool execution | tool guardrail 可提前阻止明显非法参数 |
| 禁止直接投资建议 | output guardrail + financial safety policy | eval 测误报/漏报 |
| graph edge 必须存在 | graph domain layer | Agent 只能引用 verified path |
| 写工具需授权和审批 | authorization + approval store | tool guardrail 只是额外拦截 |

同一规则多层出现时，必须说明是 defense in depth，而不是两份不同实现互相漂移。

## 9.2：Harness guardrails

当前 Harness 提供 `InputGuardrail`、`OutputGuardrail`、`ToolGuardrail` 和
`GuardrailResult`。`OutputGuardrail` 会收到原始 typed output 对象，不要先用 `str()`
把 Pydantic model 变成不稳定 repr。

至少实现并测试：

- input：secret/credential 检测；快速本地规则默认 sequential；
- output：直接 buy/sell 指令 block，缺 citation 可选择 bounded retry；
- tool call：执行前检查 URL/path/高风险参数；
- tool result：模型看见前做 secret/PII redaction；
- verdict：allow、replace、retry、block 分别映射到稳定项目状态和 trace；
- retry：计入 output retry/request budget，达到上限后进入 needs_review/failed；
- exception：guardrail 自身故障与内容被 block 是不同状态。

测试需包含引用分析师评级但并非向用户建议的反例，避免简单关键词导致高误报。任何基于
regex/keyword 的实现都必须通过 eval 集衡量 false positive/negative。

## 9.3：HITL 不等于 authorization

`approvals.py` 的服务端模型至少包含：

```text
approval_id
run_id / tool_call_id
principal / tenant
tool_name
arguments_digest
status: pending | approved | denied | expired | cancelled | consumed
requested_at / expires_at / decided_at
reviewer
decision_token_digest
```

执行链路：

```text
认证 principal
  -> scope/risk policy 允许发起
  -> 创建 pending approval
  -> reviewer approve/deny
  -> 原子 claim，校验 principal + token + TTL + arguments digest
  -> 标记 consumed
  -> 再次 execution-time permission check
  -> 执行一次
```

要求 decision token 只存 hash/digest；claim 必须原子；进程重启后状态仍在；audit log 只
追加不覆写。测试 approve、deny、expire、cancel、wrong principal、wrong token、arguments
changed、double claim 和并发 replay。

Harness deferred tool call 只负责暂停/恢复模型流程。`deferred_tools.py` 把它映射到上述
store，但不能绕过 API authentication、tenant authorization、TTL 或 replay protection。

## 9.4：Memory 与 evidence 严格隔离

Harness Memory 是模型可写的持久 notebook；它没有自动提供来源真实性。将其视为不可信、
可能含 prompt injection 的用户角色内容。

| Agent memory | FinRisk evidence/domain store |
| --- | --- |
| 调研笔记、偏好、未解决问题 | 验证后的 source/evidence/claim |
| 模型可写 | 只能由 domain policy 接纳 |
| 可被后续 prompt 读取 | 带 provenance、trust state 与 lifecycle |
| namespace 隔离 | tenant authorization + storage isolation |
| 内容可能错误/过期 | 有 source、time、validation state |

`memory_policy.py` 必须实现 promotion contract，而不是直接复制：

```text
Agent note
  -> EvidenceCandidate
  -> fetch/validate original source
  -> normalize provenance and timestamp
  -> deterministic/source-quality checks
  -> accepted evidence or needs_review
  -> claim binding
```

任何跳步都失败。测试“memory 写入 TSMC supplies X”后，该句不能自动出现在 accepted
evidence；namespace 由 `ctx.deps` 的可信 identity 解析，模型不能选择别的 tenant。

若风险收益不支持 persistent memory，可以明确拒绝采用 Harness Memory，但仍保留
promotion policy 测试，防止未来开发者把任意模型笔记当事实。

## 9.5：稳定 trace adapter

框架事件不能原样成为 API contract。`trace_adapter.py` 映射为项目稳定事件：

| 来源事件 | 项目事件 | 必须关联的 ID |
| --- | --- | --- |
| model request/response | LLM call/message | run、conversation、agent、request |
| tool call/result | tool execution | run、subgoal、tool_call |
| Graph transition | workflow transition | run、node、attempt |
| delegation | child run | parent run、child run、subgoal |
| Planning update | plan event | run、plan/task；明确非 evidence |
| spill/read | context event | run、tool_call、opaque handle |
| guardrail verdict | guardrail event | run、stage、rule |
| approval | approval audit | approval、run、tool_call、reviewer |
| memory read/write | redacted memory event | run、namespace hash、operation |
| usage | budget event | run、agent、request |

要求：

- 不记录 API key、authorization header、decision token、完整私密 prompt；
- URL query、tool arguments 和 model output 使用集中 redaction；
- error type 与 safe message 可见，traceback 只进受控内部日志；
- event schema 版本化；未知框架事件不会破坏 API serialization；
- trace 写失败的策略明确：安全/审批审计 fail closed，低风险 telemetry 可降级。

## 9.6：30-case 离线评估集

`eval/migration/cases.json` 至少包含：

| 类型 | 最低数量 | 重点 |
| --- | ---: | --- |
| filing/company risk | 8 | primary evidence、grounding |
| current market | 6 | source quality、time sensitivity |
| supply chain/graph | 6 | verified edges、missing path |
| ambiguous/conflicting | 5 | uncertainty、review |
| missing/hostile evidence | 5 | refusal、prompt injection、no fabrication |

每个 case 包含固定 fake tool responses，不能让 Core 和 Harness 在比较时访问不同网络结果。
expected 主要写不变量和允许集合，不要求整段文本完全相同。

`evaluators.py` 至少实现：

- tool selection accuracy；
- evidence coverage；
- unsupported claim rate；
- source diversity/quality；
- human-review precision/recall；
- permission violation count；
- deterministic score parity；
- trace completeness；
- requests/tool calls/tokens/latency。

优先使用确定性 evaluator。若增加 LLM judge，必须固定 judge model/version/prompt，单独记录
成本，并且不能让 judge 覆盖确定性 grounding failure。

`compare.py` 必须在关键 gate 失败时返回非零退出码。最低 release gate：

- unsupported claim rate 不恶化；
- permission violation 为 0；
- deterministic score parity 保持；
- required trace completeness 为 100%；
- approval replay 测试通过；
- 质量提升不足以抵消显著成本/延迟时不采用额外 capability。

## 9.7：live acceptance

离线测试不能证明本地/OpenAI-compatible 模型真实支持 structured output 和 tool calling。
`pydantic_ai_live_acceptance.py` 使用真实配置验证：

1. `/v1/models` 或等价健康检查；
2. 一个 typed output；
3. 一个本地 function tool call；
4. 一个 output validator/retry 或明确记录模型不支持；
5. usage、latency、messages、tool event、trace correlation；
6. secret 不出现在 stdout/report。

脚本默认不在普通 pytest 中运行，必须显式传 `--provider`/配置；任何 capability FAIL 都应
返回非零 exit code。401/403 是认证配置失败，不是 structured output 能力不支持；应保留
异常类型和安全摘要，不能只打印 `probe raised an exception`。

## 9.8：ADR、发布与回滚

ADR 必须回答：

- 为什么选择 Pydantic AI；
- Chapter 8 哪些 Harness capabilities 被采用/拒绝以及测量证据；
- 哪些确定性组件保持不变；
- provider 与 Harness 精确版本及升级策略；
- data/API/trace schema 是否需要迁移；
- cutover 是否需要 drain in-flight runs；
- offline/live gates；
- 回滚 revision/tag 与数据兼容边界；
- 为什么不保留旧 runtime feature flag。

回滚是部署上一个已验证 revision，不是在同一进程里恢复已经删除的旧 tool loop。若新旧
版本写入不同持久化格式，必须在 ADR 中定义 backward/forward compatibility 或停止点。

runbook 至少覆盖：provider 401/429/5xx、schema validation exhausted、tool timeout、plan
store failure、overflow store failure、approval stuck/replay、trace sink failure 和 eval gate
regression。

## 本章验收

```bash
uv run ruff check src/ai/governance tests/ai/governance eval/migration tests/eval
uv run pytest -q tests/ai/governance tests/eval tests/scripts
uv run python eval/migration/run_core.py
uv run --group harness python eval/migration/run_harness.py
uv run python eval/migration/compare.py
uv run pytest -q
```

有可用测试模型时再运行：

```bash
uv run python scripts/pydantic_ai_live_acceptance.py --provider sglang
uv run python scripts/pydantic_ai_release_gate.py
```

- [ ] 五层防御各有唯一主责和测试。
- [ ] guardrail verdict 与 provider/domain failure 可区分。
- [ ] approval 具备认证、授权、TTL、原子 claim 和 replay protection。
- [ ] memory 不能绕过 evidence promotion flow。
- [ ] Core/Harness/Graph/approval/memory 事件映射为稳定且脱敏的 trace。
- [ ] 30-case eval 可重复且关键 gate 以 exit code 强制执行。
- [ ] live acceptance 能区分认证、provider 能力与业务验证失败。
- [ ] ADR 与 runbook 完成；回滚不依赖旧 runtime。
- [ ] 全量回归通过，仓库中没有临时 shadow/legacy code。

本章建议提交：

```text
ch09: add production governance trace and migration evals
```

## 官方资料

- [Harness guardrails](https://pydantic.dev/docs/ai/harness/guardrails/)
- [Harness memory](https://pydantic.dev/docs/ai/harness/memory/)
- [Pydantic AI deferred tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/)
- [Pydantic AI testing](https://pydantic.dev/docs/ai/guides/testing/)
- [Pydantic Evals](https://pydantic.dev/docs/ai/evals/)
