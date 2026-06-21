# Step 12 - 当前实现审核、稳定化修正与下一步功能

## 目标

本步骤记录对当前代码实现的审核结果，并把修正优化方案转成可执行任务。

当前项目已经实现了大量 roadmap 骨架：

- shared schemas
- Hugging Face EDGAR loader
- SEC client
- transcript providers
- SearchRouter
- Agent runtime
- extraction/risk/sentiment/opportunity/report agents
- Neo4j graph writer/query
- offline MVP demo
- evaluation helpers

但当前状态仍属于“功能骨架已铺开，稳定性和真实闭环不足”。下一阶段不建议继续扩展新模块，应先把测试、数据流、报告质量和真实数据接入稳定下来。

## 当前验证结果

### 测试

直接运行：

```bash
uv run pytest -q
```

结果：

- 失败于测试收集阶段。
- 主要错误是 `ModuleNotFoundError: No module named 'src'`。

加上 `PYTHONPATH=.` 后：

```bash
PYTHONPATH=. uv run pytest -q
```

结果：

- 336 passed
- 1 skipped
- 4 failed

4 个失败集中在：

- `BrowserWrapper.close()` 在未安装 `agent-browser` 时抛 `FileNotFoundError`
- Slack token sanitizer 测试样例与实际 pattern 不匹配

### MVP demo

运行：

```bash
PYTHONPATH=. uv run python -m src.pipelines.analyze_company --ticker DEMO --offline-fixtures
```

结果：

- 可以生成 Markdown 报告。
- 说明 offline MVP 主流程已经能跑通。

但报告质量仍有问题：

- `Key Evidence` 存在重复 evidence。
- `Supply Chain Map` 为空。
- opportunity hypothesis 有重复和泛化问题。
- sentiment 判断较粗糙。

### Ruff

运行：

```bash
PYTHONPATH=. uv run ruff check .
```

结果：

- 当前全仓有大量 lint 问题。
- 许多来自历史脚本和测试文件，也有部分来自新模块。

短期不应把全仓 ruff 作为 merge gate，建议先收窄到新核心代码。

## P0 修正任务：让测试默认可运行

### 问题

`uv run pytest -q` 默认无法 import `src` 和 `scripts`。

### 涉及文件

```text
pyproject.toml
```

### 修正方案

添加 pytest 配置：

```toml
[tool.pytest.ini_options]
pythonpath = ["."]
markers = [
    "integration: tests that require external services or network access",
]
```

### 验收标准

运行：

```bash
uv run pytest -q
```

不再出现 `ModuleNotFoundError: No module named 'src'`。

## P0 修正任务：BrowserWrapper 缺少 agent-browser 时应优雅降级

### 问题

当前 `BrowserWrapper.close()` 直接执行：

```python
subprocess.run(["agent-browser", "close"], capture_output=True, timeout=5)
```

如果本机没有安装 `agent-browser`，普通单元测试会失败。

### 涉及文件

```text
src/browser/wrapper.py
tests/browser/test_wrapper.py
tests/browser/test_explorer.py
```

### 修正方案

`close()` 应该作为 best-effort cleanup：

```python
def close(self) -> None:
    """Clean up browser resources."""
    try:
        subprocess.run(
            ["agent-browser", "close"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    if self._process:
        self._process.terminate()
        self._process = None
```

同时建议 `_run_command()` 捕获：

- `FileNotFoundError`
- `subprocess.TimeoutExpired`

并返回：

```python
return False, "agent-browser not available", self._current_url
```

### 验收标准

未安装 `agent-browser` 时：

```bash
uv run pytest tests/browser/test_wrapper.py tests/browser/test_explorer.py -q
```

不因 `FileNotFoundError` 失败。

## P0 修正任务：修复 Slack token sanitizer 测试或 pattern

### 问题

测试使用：

```python
text = "Slack token: ******->*****"
```

但 sanitizer 当前只匹配真实 Slack token 格式：

```python
r"xox[baprs]-[A-Za-z0-9]{10,}"
```

`******->*****` 是脱敏占位符，不是真实 token。

### 涉及文件

```text
src/browser/sanitize.py
tests/browser/test_sanitize.py
```

### 推荐修正方案

修改测试为合成 Slack token：

```python
def test_sanitize_slack_token():
    token = "xoxb-" + "a" * 20
    text = f"Slack token: {token}"
    result = sanitize_snapshot(text)
    assert token not in result
    assert "[TOKEN]" in result
```

如果确实需要识别已脱敏占位符，可以额外增加 pattern，但优先级较低。

### 验收标准

```bash
uv run pytest tests/browser/test_sanitize.py -q
```

通过。

## P1 修正任务：报告 evidence 去重

### 问题

offline demo 报告中 `Key Evidence` 出现重复 evidence，典型表现为 `[1]`、`[2]` 重复列出。

原因是 report index 已经去重，但 `_key_evidence()` 遍历原始 `evidence` list。

### 涉及文件

```text
src/agents/report_agent.py
tests/agents/test_report_agent.py
tests/pipelines/test_analyze_company.py
```

### 修正方案

选择其中一种：

1. 在 `ReportAgent.generate()` 开头对 evidence 去重。
2. 修改 `_key_evidence()`，跳过已经输出过的 `evidence_id`。

推荐实现：

```python
def _dedupe_evidence(self, evidence: list[Evidence]) -> list[Evidence]:
    seen: set[str] = set()
    deduped: list[Evidence] = []
    for ev in evidence:
        if ev.evidence_id in seen:
            continue
        seen.add(ev.evidence_id)
        deduped.append(ev)
    return deduped
```

并在 `generate()` 中统一使用 deduped evidence。

### 验收标准

- 报告 `Key Evidence` 中每个 `evidence_id` 只出现一次。
- `Sources` 和正文引用编号一致。

## P1 修正任务：把 extraction pipeline 接入 MVP 主流程

### 问题

offline demo 中，filing 和 transcript 都包含供应链信息，但报告显示：

```text
No supply chain claims were identified.
```

当前 `analyze_company()` 主要跑 risk/sentiment/policy_geo，并没有把 `FilingAgent`、`TranscriptAgent`、`WebAgent` 的实体关系抽取接入主流程。

### 涉及文件

```text
src/pipelines/analyze_company.py
src/pipelines/extract_from_filing.py
src/pipelines/extract_from_transcript.py
src/pipelines/extract_from_web.py
src/agents/filing_agent.py
src/agents/transcript_agent.py
src/agents/web_agent.py
tests/pipelines/test_analyze_company.py
tests/fixtures/demo_filing.json
tests/fixtures/demo_transcript.json
tests/fixtures/demo_web_results.json
```

### 修正方案

在 `analyze_company()` 中加入 extraction 阶段：

```text
filings -> FilingAgent / extract_from_filing
transcripts -> TranscriptAgent / extract_from_transcript
web_evidence -> WebAgent / extract_from_web
```

并把结果合并到：

- `state.entities`
- `state.relations`
- `state.claims`
- `state.evidence`

最小可行版本可以先用规则抽取供应链 claim：

- 句子包含 `supplier`、`supplier base`、`component sourcing`
- 句子包含 `supply chain`、`shipping disruption`
- 句子包含 `customer`、`partner`、`vendor`

输出 `claim_type="supply_chain"`，并带原始 evidence。

### 验收标准

运行 offline demo：

```bash
uv run python -m src.pipelines.analyze_company --ticker DEMO --offline-fixtures
```

报告中 `Supply Chain Map` 不为空，并至少包含一条带 citation 的供应链 claim。

## P1 修正任务：减少重复和泛化 opportunity hypothesis

### 问题

offline demo 中会生成多个重复的 `Demand acceleration hypothesis`，内容泛化，信息密度较低。

### 涉及文件

```text
src/agents/opportunity_agent.py
tests/agents/test_opportunity_agent.py
```

### 修正方案

1. 按 `hypothesis_type + supporting_claim_ids` 去重。
2. fallback hypothesis 最多 1 条。
3. 优先级排序：
   - supply_chain_opportunity
   - policy_beneficiary
   - geopolitical_substitution
   - sentiment_turnaround
   - risk_mispricing
   - demand_acceleration
4. 若 evidence 不足，不强行凑满 3 条；宁可输出 1-2 条高质量 hypothesis。

### 验收标准

- 同一报告中不出现标题和 statement 完全相同的 hypothesis。
- 每条 hypothesis 至少有一条 evidence。
- `confidence` 不应因为 fallback 被抬高。

## P1 修正任务：实现 ticker -> CIK resolver

### 问题

live SEC fetch 当前不可用，代码直接抛：

```python
raise RuntimeError("ticker->CIK mapping not yet implemented")
```

### 涉及文件

```text
src/data/sec_client.py
src/data/filing_fetcher.py
src/data/ticker_resolver.py
src/pipelines/analyze_company.py
tests/data/test_ticker_resolver.py
```

### 修正方案

新增 `TickerResolver`：

```python
class TickerResolver:
    def resolve(self, ticker: str) -> CompanyIdentifier:
        ...
```

数据来源优先级：

1. 本地 cache
2. SEC company tickers JSON
3. 手动 fixture fallback

建议 schema：

```python
class CompanyIdentifier(BaseModel):
    ticker: str
    cik: str
    name: str | None = None
```

### 验收标准

```python
resolver.resolve("AAPL").cik == "0000320193"
```

`analyze_company --ticker AAPL --no-web --no-transcripts` 至少能尝试获取 SEC filing metadata。

## P1 修正任务：统一 Neo4j entity key

### 问题

Graph writer 写实体时使用 label-specific key：

```cypher
MERGE (n:Company { company_id: $entity_id })
```

但 schema 和 query 语义都以 `entity_id` 为统一主键。当前设计容易导致重复节点和查询不一致。

### 涉及文件

```text
src/graph/writer.py
src/graph/schema.cypher
tests/graph/test_writer.py
```

### 修正方案

统一改为：

```cypher
MERGE (n:Company { entity_id: $entity_id })
```

所有实体 label 都用 `entity_id` 作为唯一 key。

### 验收标准

- `schema.cypher` 中所有实体约束使用 `entity_id`。
- `GraphWriter.write_entity()` 生成 Cypher 使用 `entity_id`。
- `write_extraction_result()` 重复运行不会产生重复节点。

## P2 修正任务：收窄 Ruff 门禁并逐步清理

### 问题

全仓 `ruff check .` 当前有大量问题，包含历史脚本和测试中的 line length、magic number、local import 等。

### 修正方案

短期在 CI 或开发命令中只检查核心新代码：

```bash
uv run ruff check src/schemas src/data src/agents src/graph src/pipelines src/tools/search_router.py src/tools/search_cache.py
```

中期再逐步清理：

1. `src/`
2. `tests/`
3. `scripts/`
4. `docs/`

### 验收标准

核心新代码 ruff 通过后，再扩大检查范围。

## P2 修正任务：提升 sentiment 质量

### 问题

offline demo 里 prepared remarks 包含正面和负面信号，但输出为：

```text
Prepared remarks tone: negative.
```

当前情绪分析偏关键词规则，容易过度受负面词影响。

### 涉及文件

```text
src/agents/sentiment_agent.py
src/pipelines/analyze_sentiment.py
tests/agents/test_sentiment_agent.py
```

### 修正方案

1. 分别计算 positive、negative、uncertainty、defensiveness。
2. 如果正负信号同时存在，输出 `mixed`。
3. Analyst question 不计入 management sentiment。
4. Operator turn 不计入 sentiment。
5. Q&A 中只有 management answer 参与管理层情绪。

### 验收标准

demo transcript 中：

- prepared remarks 应为 `mixed` 或带 topic-level 正负拆分。
- analyst question 不生成管理层观点。
- operator turn 不影响情绪。

## P2 修正任务：真实 provider 集成测试

### 目标

在 offline demo 稳定后，再验证真实数据源。

### 建议命令

SEC：

```bash
RUN_SEC_INTEGRATION=1 uv run pytest tests/data/test_sec_client.py -m integration
```

Transcript：

```bash
RUN_TRANSCRIPT_INTEGRATION=1 uv run pytest tests/data/providers -m integration
```

Search：

```bash
RUN_SEARCH_INTEGRATION=1 uv run pytest tests/tools/providers -m integration
```

Neo4j：

```bash
RUN_NEO4J_INTEGRATION=1 uv run pytest tests/graph -m integration
```

## 推荐执行顺序

1. P0：pytest pythonpath 配置。
2. P0：BrowserWrapper best-effort cleanup。
3. P0：Slack token 测试修正。
4. P1：Report evidence 去重。
5. P1：Extraction pipeline 接入 `analyze_company()`。
6. P1：Opportunity 去重和质量控制。
7. P1：TickerResolver。
8. P1：Neo4j entity key 统一。
9. P2：核心目录 ruff 清理。
10. P2：真实 provider 集成测试。

## 下一步功能优先级

稳定化完成后，再进入下一轮功能：

1. 真实 SEC filing 端到端：ticker -> CIK -> latest 10-K -> section extraction。
2. transcript provider 真数据拉取：FMP 或 Alpha Vantage 至少跑通一个。
3. supply chain extraction 从规则版升级到 LLM structured output。
4. Neo4j 图查询接入 opportunity discovery。
5. SearchRouter provider 优先级配置化。
6. 报告加入 graph paths 和 counter-evidence scoring。

## 完成定义

本稳定化步骤完成后，应满足：

```bash
uv run pytest -q
uv run python -m src.pipelines.analyze_company --ticker DEMO --offline-fixtures
```

两条命令都能在无 API key、无 Neo4j、无 agent-browser 的机器上稳定通过。

