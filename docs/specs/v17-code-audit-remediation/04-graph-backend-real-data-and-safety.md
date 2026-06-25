# 04 - Graph Backend、真实数据接入与叙事安全

## 目标

补齐 graph retriever backend、真实数据模式和 graph narrative 安全表达，避免图路径解释被误读为确定性预测或投资建议。

## 涉及文件

```text
src/graph_reasoning/backends.py
src/graph_reasoning/subsystem.py
src/graph_reasoning/path_interpreter.py
src/workflows/steps/market_explorer_step.py
src/workflows/steps/filing_risk_extractor.py
src/tools/search_router.py
tests/graph_reasoning/test_backends.py
tests/graph_reasoning/test_path_interpreter_safety.py
tests/workflows/test_real_mode_fallbacks.py
```

## GraphPathBackend

新增或完善：

```python
class GraphPathBackend(Protocol):
    def retrieve(self, context: GraphQueryContext) -> list[CandidateGraphPath]:
        ...
```

实现：

```text
FixtureGraphBackend
Neo4jGraphBackend
```

`GraphReasoningSubsystem` 支持注入：

```python
GraphReasoningSubsystem(backend=FixtureGraphBackend())
GraphReasoningSubsystem(backend=Neo4jGraphBackend(client))
```

## FixtureGraphBackend

要求：

- 离线可运行。
- 用于 demo mode 和 tests。
- 返回确定性 paths。
- path ids 稳定。

## Neo4jGraphBackend

要求：

- 接收 `Neo4jClient`。
- 根据 `GraphQueryContext` 查询 upstream / exposure paths。
- depth 参数必须白名单。
- Neo4j 异常不直接炸 workflow，应返回 guardrail finding 或 fallback event。

## Graph Narrative Safety

当前不安全表达：

```text
creates a {confidence_pct}% probability of supply disruption
```

替换为：

```text
This path suggests a plausible exposure channel with path confidence {score}.
It does not prove immediate financial impact and should be treated as a research hypothesis.
```

禁止词/短语：

```text
probability of supply disruption
guaranteed
buy
sell
should invest
must invest
price target
```

Graph insight 字段使用：

```text
research_theme
```

不要使用：

```text
investment_theme
```

## Real Mode 数据接入

### MarketExplorerStep

现状问题：

```text
real mode 未注入 router 时可能返回空
```

要求：

- 默认构造 `SearchRouter`。
- search/browser 失败时写入 `FallbackEvent`。
- real mode 可退回 cached fixture。
- 返回 evidence 时必须有 source URL 或明确 cached source。

### FilingRiskExtractorStep

要求：

- 增加 LLM structured extractor adapter。
- LLM failure 使用 keyword fallback。
- SEC failure 使用 cached/demo fixture。
- fallback 写入 state。

## Integration Test 开关

不要让 CI 默认依赖外部网络。

新增 marker 或 env：

```bash
RUN_SEC_INTEGRATION=1 uv run pytest tests/data -m integration
RUN_SEARCH_INTEGRATION=1 uv run pytest tests/tools -m integration
```

默认：

```text
skip integration tests
```

## 测试要求

新增：

```text
tests/graph_reasoning/test_backends.py
tests/graph_reasoning/test_path_interpreter_safety.py
tests/workflows/test_real_mode_fallbacks.py
```

测试用例：

- fixture backend 离线可用。
- Neo4j backend 可用 mock client 返回 CandidateGraphPath。
- backend 异常变成 guardrail finding。
- path interpreter 不输出禁止短语。
- graph insight 使用 `research_theme`。
- MarketExplorerStep 未注入 router 时仍能默认构造。
- SearchRouter failure 写入 fallback event。
- FilingRiskExtractorStep LLM failure 使用 fallback。

验收命令：

```bash
uv run pytest tests/graph_reasoning/test_backends.py tests/graph_reasoning/test_path_interpreter_safety.py -q
uv run pytest tests/workflows/test_real_mode_fallbacks.py -q
```

