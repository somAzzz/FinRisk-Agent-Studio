# Chapter 14：Typed Climate Evidence Agent 与验证链

## 本章结果

本章复用 Chapter 6–9 已完成的 FinRisk Pydantic AI runtime，只新增两个专用 Agent：证据抽取器和
逐 requirement verifier。确定性代码先验证 quote/span/hash，指标 parser 负责数值真值；模型不
直接决定最终 assessment。

前置条件：Chapter 13 已能为固定 requirement 产生带 provenance 的 context package。

## 设计决定

1. 不复制 TCFD 仓库的 keyword/relevance Agent；只复用 prompt 约束和困难负例经验。
2. Agent factory 位于 `src/ai/agents/climate/`，domain models 仍位于 `src/domains/climate/`。
3. extractor 只提出 evidence 与 mapping，verifier 对每个 mapping 独立判断。
4. quote 的存在性和 offset 由 Python 校验，不能靠模型自报“原文一致”。
5. provider、schema、validation、budget 和 domain failure 分开记录。
6. 数值的 raw value/unit/period 不由叙述性摘要重新生成。

## 文件变更总览

### 新建

```text
src/ai/agents/climate/__init__.py
src/ai/agents/climate/models.py
src/ai/agents/climate/evidence_extractor.py
src/ai/agents/climate/verifier.py
src/domains/climate/metrics.py
src/evaluation/validators/climate_locator_validator.py
src/evaluation/validators/climate_mapping_validator.py
src/workflows/steps/climate_evidence_extractor.py
src/workflows/steps/climate_verifier.py
tests/ai/agents/climate/
tests/domains/climate/test_metrics.py
tests/evaluation/test_climate_validators.py
tests/workflows/test_climate_agent_steps.py
```

### 复用，不复制

- `src/ai/model_factory.py`
- `src/ai/deps.py`
- `src/ai/usage.py`
- `src/ai/recorder.py`
- `src/ai/runtime_adapter.py`
- `src/schemas/tool_trace.py`
- `src/evaluation/engine.py`

如果新 Agent 需要 runtime 能力，优先扩展共享的最小协议并为所有调用方补测试，不创建
`climate_model_factory.py` 或私有 OpenAI client。

## 14.1：输入任务合同

不要把整份 workflow state 塞进 prompt。定义最小 typed task：

```text
ClimateEvidenceTask
  run_id, document_ref, requirement,
  candidate_contexts, allowed_requirement_ids,
  extraction_revision, data_policy

ClimateVerificationTask
  requirement, evidence, proposed_mapping,
  source_blocks, verification_revision
```

`AgentDeps` 提供 run-scoped services、permissions、budget 和 recorder；任务输入提供本次业务数据。
模型看不到未授权 document、其他 tenant、完整 registry 或任意文件系统。

## 14.2：Evidence extractor output

输出应是批量 typed model，例如：

```text
ClimateEvidenceProposalBatch
  proposals[]
  rejected_candidate_ids[]
  warnings[]

ClimateEvidenceProposal
  candidate_ids[]
  quote
  block_id
  char_start / char_end
  evidence_type
  climate_topics[]
  claim_summary
  proposed_requirement_relations[]
```

output validator 在 bounded retry 前检查：

- block ID 必须属于任务输入；
- requirement ID 必须在 allowlist；
- quote 非空且 offset 范围合法；
- quote 与 block 精确一致；
- evidence type/topic 必须来自 taxonomy；
- claim summary 不得引入 quote 外实体、数值或时间。

不可修复的 locator 错误成为 `model_output` failure，不把该 proposal 保存为空 evidence。

## 14.3：防 prompt injection

system instruction 明确报告内容是不可信数据。context package 使用结构化边界标识，并测试报告中
出现以下内容时不会改变任务：

- “忽略前面的规则”；
- 请求读取 secret/其他文件；
- 要求把文本判为合规；
- 伪造 JSON/system message；
- 在表格中嵌入工具调用指令。

不要把“不要被注入”只写在 prompt。Agent 不获得 shell/file/network tool，本地 validator 拒绝
未知 ID，data policy 和 tool permissions 仍在执行边界生效。

## 14.4：逐 mapping verifier

verifier 输出：

```text
VerificationOutput
  mapping_id
  verdict: supported | partial | unsupported | uncertain
  reason_codes[]
  rationale
  supporting_span_ids[]
  missing_elements[]
```

要求：

- 每个 requirement 独立验证；一条 evidence 对 A supported 不代表对 B supported；
- rationale 只能解释输入 requirement 与 evidence 的关系；
- unsupported/uncertain 不进入肯定聚合；
- verifier 失败保留 proposed mapping 和 failure，但不创建否定 decision；
- extractor/verifier 同一模型时如实记录，不称为 independent model verification。

## 14.5：确定性 locator gate

调用 verifier 前按固定顺序：

```text
candidate and block identity exists
  -> document/hash match
  -> offset in range
  -> exact quote match
  -> context package authorization
  -> proposed mapping schema valid
  -> semantic verifier
```

前五步失败不消耗 verifier 请求；记录精确 reason code。Unicode normalization 只能用于诊断，不能
用 normalized fuzzy match 冒充 exact source match。

## 14.6：Metric parser

`src/domains/climate/metrics.py` 是纯函数/规则模块：

- 从 verified quote 或 table cells 解析 raw value；
- 显式处理千/百万/十亿、百分比、负号、币种、tCO2e 等单位；
- 期间、Scope、组织边界和 actual/target 必须来自定位上下文；
- normalization 保留 rule ID、输入、输出和 rounding；
- 不确定单位/表头生成 issue，normalized value 为 `None`；
- 模型可提出 metric type，但不能覆盖 raw cell。

## 14.7：失败、并发和 trace

复用 FinRisk budget、usage 和 recorder，按 item 守恒：

```text
each input candidate/mapping
  -> success object
  OR structured failure
  OR pending human review
```

并发有上限且输出按稳定 ID 排序。记录 model/provider、endpoint policy、prompt/Agent revision、
registry、requests/tokens、latency、retry 和 validation errors。日志不保存未脱敏整份 context。

## 14.8：测试策略

| 层 | 方法 |
| --- | --- |
| Agent schema | `TestModel` 检查 output/tool schema |
| 精确行为 | `FunctionModel` 产生正确、错误、重试和越界输出 |
| locator | 纯函数测试 exact span/hash |
| metric | 表格/单位/期间 fixtures |
| workflow | fake Agents 验证并发、顺序、partial failure |
| live eval | 显式 provider，默认 pytest 禁止网络 |

困难负例来自旧 eval 原则，但 gold 需要改成 requirement + span + verdict，不能直接把关键词 expected
列表当 evidence gold。

## 本章验收

```bash
uv run pytest -q \
  tests/ai/agents/climate \
  tests/domains/climate/test_metrics.py \
  tests/evaluation/test_climate_validators.py \
  tests/workflows/test_climate_agent_steps.py
uv run ruff check src/ai/agents/climate src/domains/climate src/evaluation/validators
uv run mypy src
```

- [ ] 新 Agent 使用统一 model factory、AgentDeps、usage 和 recorder。
- [ ] domain package 不 import Pydantic AI。
- [ ] 所有 accepted quote 通过 exact locator gate。
- [ ] verifier 逐 mapping 工作，失败不产生否定结论。
- [ ] metric raw value 和 locator 永远保留。
- [ ] provider failure、output failure、unsupported 和 uncertain 可区分。

本章建议提交：

```text
ch14: add typed climate evidence extraction and verification
```
