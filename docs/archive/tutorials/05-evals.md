# Chapter 5：用离线测试、Golden Cases 与 Live Acceptance 验收系统

> 当前实现导读。架构迁移正确、workflow 回归稳定、模型输出质量和真实 provider 兼容性是四个
> 不同问题，必须使用不同证据回答。

## 本章结果

完成本章后，你应能解释：

- `TestModel`、`FunctionModel`、fixture workflow 和 live provider 各自适合验证什么；
- 当前 30-case matrix 的真实覆盖范围；
- Agent golden cases 如何评价 tool choice 和 evidence discipline；
- source/import gate 如何防止旧 runtime 回归；
- 当前 eval 体系距离完整模型质量 benchmark 还有什么差距。

## 当前文件地图

| 文件 | 当前职责 |
| --- | --- |
| `tests/conftest.py` | 默认禁止真实模型请求 |
| `tests/ai/` | model、Agent、toolset、adapter、message、approval 等合同测试 |
| `tests/ai/graphs/` | Graph parity、reducer 和并行安全 |
| `tests/evaluation/` | guardrail、quality layer 和 release matrix |
| `tests/test_import_all_modules.py` | import/source migration gate |
| `eval/golden_cases.json` | 30 个 workflow/guardrail 场景描述 |
| `eval/run_eval.py` | 离线 demo fixture runner |
| `src/evaluation/agent_eval.py` | Agent tool/evidence/review deterministic evaluator |
| `tests/fixtures/agent_golden_cases/` | 两个 Agent trace fixtures |
| `scripts/pydantic_ai_live_acceptance.py` | 真实 provider capability 验收 |
| `scripts/real_data_acceptance.py` | 真实数据路径验收 |

## 5.1：测试金字塔

### Pydantic model tests

验证字段范围、extra fields、validator 和序列化，不需要模型。

### `TestModel`

适合验证 Agent wiring、typed output、工具 schema 和简单调用。它不评价金融回答质量。

### `FunctionModel`

可以精确控制每一轮 `ModelResponse`，适合测试 tool call、output tool、retry 和错误路径。

### Fixture workflow

用确定性 SEC/market/graph fixture 验证完整 state、trace、report 和 quality gate，不依赖网络。

### Live acceptance

只在显式命令下访问 provider，证明真实 endpoint 能完成最低 structured output 和 tool calling。

## 5.2：默认测试禁止网络

`models.ALLOW_MODEL_REQUESTS = False` 是全局安全门。单元测试如果意外创建真实
`OpenAIChatModel` 请求，会立即失败。

不要通过在 CI 中注入真实 API key 来“修复”这种失败。需要网络的测试应单独标记 integration，
并使用明确脚本或选择参数运行。

## 5.3：Graph parity 与迁移门禁

Graph 测试不仅检查“能跑完”，还比较迁移前后公共 state 的关键部分：风险、证据、评分、报告、
nodes/links、Sankey、evaluation 和 trace。

`tests/test_import_all_modules.py` 负责另一类问题：

- 所有 `src` 模块可导入；
- 已删除的 runtime/client 文件不能回来；
- `LLMToolAgentRuntime` 等旧符号不能进入生产；
- `src.llm`、直接 `chat.completions` 和旧 JSON client 模式不能重新出现。

这是架构 gate，不评价模型答案。

## 5.4：30-case workflow matrix

`eval/golden_cases.json` 覆盖 bank、SaaS、semiconductor、energy、biotech、foreign issuer、
restatement、source conflict、provider missing 和 no-change 等 30 个场景。

`eval/run_eval.py` 当前输出：

```text
final status
evidence coverage
financial advice risk
unsupported claim count
schema validity
source diversity
hallucination risk
forbidden phrases
```

必须准确理解它的限制：

- 所有 case 当前共享同一 AAPL demo fixture；
- runner 不逐项断言 `expected_risk_types`；
- case prompt 表达跨行业风险，但数据不是 30 家公司的真实 gold evidence；
- 只有 `fail` 返回非零，`needs_review` 当前仍返回成功退出码。

因此它证明 workflow/guardrail 稳定性，不证明 30 家公司的结论正确。

## 5.5：Agent golden cases

`AgentGoldenCase` 固定 tool events，并声明：

```text
expected tool families
minimum accepted/rejected candidates
whether review is expected
disallowed terms
```

`evaluate_agent_golden_case()` 使用 `EvidenceCandidateNormalizer`，确定性计算：

- tool choice score；
- evidence discipline score；
- stop/review score；
- safety boundary；
- final verdict。

当前 fixture 只有 Apple supply-chain 和 insufficient-evidence 两例，适合做合同回归，还不足以成为
广泛的 Agent benchmark。

## 5.6：组件级评价

当前还包括：

- `evaluate_extraction()`：entity/relation ID overlap、unsupported claims、evidence coverage；
- `evaluate_report()`：citation、免责声明、counter-evidence 和禁止措辞；
- source-diversity 与 hallucination-risk metrics；
- claim/evidence/source/financial-safety validators；
- memory/context guardrails；
- 财务勾稽与真实数据 acceptance。

优先使用确定性 evaluator。若未来增加 LLM judge，必须固定 judge model、prompt 和版本，并且不能
覆盖确定性 grounding failure。

## 5.7：Live capability 不等于 live quality

`pydantic_ai_live_acceptance.py` 证明 provider 能：

- 调用一个本地 typed tool；
- 返回一个严格 typed output；
- 报告 usage；
- 在失败时输出脱敏错误并返回非零。

它不把预测与人工 gold label 比较，也不计算 precision/recall/F1。因此“live acceptance 通过”只
表示技术协议兼容，不能表示金融研究质量达标。

## 5.8：当前 eval 缺口

若未来加强模型质量评估，优先补：

1. filing risk、supplier relation 和 research grounding 的版本化 gold dataset；
2. entity/relation/claim 分开的 precision、recall 和 F1；
3. empty-output accuracy、retry/failure 分类、latency 和 usage；
4. 每个 case 独立且匹配业务的 fixture；
5. timestamped、不可覆盖的 live quality report；
6. 更系统的 AST dependency-direction 和 silent-empty-success gate。

这些属于后续质量工程，不应在当前文档中写成已实现。

## 5.9：练习与验收

核心离线检查：

```bash
uv run python -m pytest -q tests/ai tests/evaluation
uv run python -m pytest -q tests/test_import_all_modules.py
uv run python eval/run_eval.py
```

真实服务可用时再选择性运行：

```bash
uv run python scripts/pydantic_ai_live_acceptance.py \
  --provider sglang
uv run python scripts/real_data_acceptance.py --help
```

- [ ] 单元测试不会访问真实 provider。
- [ ] architecture gate 与 quality eval 没有混为一类。
- [ ] 30-case matrix 的共享 fixture 限制被明确说明。
- [ ] live capability probe 没有被描述成金融质量 benchmark。
- [ ] failed 与 needs_review 的退出语义清楚。
- [ ] 未实现的 PR/F1 和 live-quality runner 被列为缺口而非现状。

完成 Chapter 0–5 后，再进入 Chapter 6，学习当前 typed toolsets、权限与执行 trace 的具体实现。
