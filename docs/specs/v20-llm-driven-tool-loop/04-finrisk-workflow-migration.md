# 04 - FinRisk Workflow Migration

## 目标

将 FinRisk workflow 中“需要外部信息选择”的步骤迁移到 LLM-driven tool loop，同时保留 deterministic quality gates。

不把整个 workflow 变成无约束 agent。迁移重点是：

- LLM 决定查什么、fetch 哪些 URL、是否需要 filing/transcript/financial metrics。
- 后端执行工具。
- workflow 负责验证 evidence、risk schema、quality gates、report safety。

## 现状

`MarketExplorerStep` 当前直接：

```python
response = router.search(risk.risk_factor, intent="supply_chain")
legacy = to_evidence(response)
```

这保证了可测性，但 LLM 不能根据上下文自主决定：

- 搜哪些 query。
- 是否 fetch 结果页。
- 是否查询 transcript。
- 是否补 financial metrics。
- 何时停止。

## 迁移目标

新增：

```text
src/workflows/steps/llm_market_explorer_step.py
```

或扩展现有 `MarketExplorerStep`：

```python
MarketExplorerStep(mode="deterministic" | "llm")
```

## LLM-visible tools

FinRisk market scope 初期允许：

- `web_search`
- `web_fetch`
- `search_and_fetch`
- `transcript_lookup`
- `financial_metrics_lookup`

后续允许：

- `sec_list_filings`
- `sec_fetch_filing`
- `xbrl_fact_lookup`

不允许：

- graph write。
- report write。
- memory write。

## Prompt contract

System prompt 应包含：

- 当前任务是 evidence collection，不是投资建议。
- 每个 claim 必须能被 source 支撑。
- 优先找最近、高质量、可访问来源。
- 若只得到 snippet，必要时使用 `web_fetch`。
- 输出 final answer 时区分：
  - evidence found
  - inference
  - uncertainty
  - suggested next checks

## 输出转换

LLM final answer 不直接进入 `MarketEvidence`。

工具结果进入：

```text
ToolExecutionEvent
    → EvidenceCandidate
    → EvidenceNormalizerStep
    → MarketEvidence
```

即使 LLM final answer 很好，也只能作为 narrative/context，不能替代 evidence normalization。

## Workflow 状态扩展

建议在 `FinRiskWorkflowState` 增加：

```python
llm_tool_runs: list[LLMToolRunResult]
tool_events: list[ToolExecutionEvent]
```

或把这些并入现有 trace/audit log。

## 迁移步骤

### Step 1 - Shadow mode

在真实模式中同时运行：

- deterministic `SearchRouter.search`
- LLM-driven `LLMToolAgentRuntime`

只使用 deterministic 结果进入 report，LLM 结果写 trace。

### Step 2 - Evidence candidate mode

LLM tool outputs 转成 evidence candidates，但必须经过 EvidenceNormalizer。

### Step 3 - Primary mode

LLM-driven market explorer 成为 real mode 主路径；deterministic router 作为 fallback。

### Step 4 - Quality-gated mode

若 LLM tool run 没有足够 evidence 或 source quality 低，自动 fallback deterministic/cached。

## 测试

新增：

```text
tests/workflows/test_llm_market_explorer_step.py
```

覆盖：

- shadow mode 不改变当前报告结果。
- mock LLM 请求 `web_search` 后，工具结果进入 trace。
- mock LLM 请求 `web_fetch` 后，fetch content 转 evidence candidate。
- unknown tool 不进入 evidence。
- low-quality source 触发 fallback event。

## 验收

```bash
uv run pytest tests/workflows/test_llm_market_explorer_step.py tests/workflows -q
```
