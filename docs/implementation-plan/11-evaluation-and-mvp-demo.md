# Step 11 - 评测体系与 MVP 端到端 Demo

## 目标

建立最小可用端到端 demo，并为后续迭代提供评测体系。

最终用户应能运行：

```bash
python -m src.pipelines.analyze_company --ticker AAPL --year 2024
```

并得到一个带 evidence 的研究报告。

## 需要新增或修改的文件

新增：

```text
src/pipelines/analyze_company.py
src/evaluation/__init__.py
src/evaluation/extraction_eval.py
src/evaluation/graph_eval.py
src/evaluation/report_eval.py
scripts/demo_analyze_company.py
tests/pipelines/test_analyze_company.py
tests/evaluation/test_extraction_eval.py
tests/evaluation/test_report_eval.py
```

可选新增：

```text
docs/mvp-demo.md
```

## MVP 流程

输入：

```text
ticker=AAPL
year=2024
```

流程：

1. 解析 ticker 到 CIK。
2. 获取最新 10-K 或 Hugging Face 历史 filing。
3. 获取最近 1-4 次 transcript。
4. 执行网页搜索获取 recent evidence。
5. 抽取实体、关系和 claim。
6. 写入 Neo4j，如果 Neo4j 不可用则跳过并提示。
7. 分析管理层情绪、政策风险、地缘政治风险。
8. 发现机会 hypothesis。
9. 生成 Markdown report。

## CLI 设计

```bash
python -m src.pipelines.analyze_company \
  --ticker AAPL \
  --year 2024 \
  --max-transcripts 4 \
  --max-web-results 5 \
  --write-graph \
  --output reports/AAPL-2024.md
```

参数：

- `--ticker` 必填
- `--year` 可选
- `--max-transcripts`
- `--max-web-results`
- `--write-graph`
- `--no-web`
- `--no-transcripts`
- `--output`

## Offline Demo Mode

为了测试稳定，必须支持 offline demo。

建议：

```bash
python -m src.pipelines.analyze_company --ticker DEMO --offline-fixtures
```

fixtures：

```text
tests/fixtures/demo_filing.json
tests/fixtures/demo_transcript.json
tests/fixtures/demo_web_results.json
```

这样 CI 和其它编程助手不需要 API key 也能验证端到端流程。

## 评测体系

### Extraction Eval

指标：

- entity precision sample
- relation precision sample
- evidence coverage
- unsupported claim rate

初版可基于 golden fixture：

```python
class ExtractionEvalResult(BaseModel):
    expected_entities: int
    matched_entities: int
    expected_relations: int
    matched_relations: int
    unsupported_claims: int
    evidence_coverage: float
```

### Graph Eval

指标：

- duplicate entity rate
- relation without evidence count
- orphan evidence count
- query success rate

### Report Eval

指标：

- every claim has citation
- disclaimer exists
- counter-evidence section exists
- no forbidden investment advice phrases

禁用短语示例：

- "buy now"
- "guaranteed"
- "must rise"
- "必然上涨"
- "强烈买入"

## 测试策略

测试覆盖：

- offline demo 可跑完。
- report 文件生成。
- 无 Neo4j 时 graceful degradation。
- 无 API key 时跳过对应 provider。
- report eval 检测免责声明。
- unsupported claim rate 可计算。

## 验收标准

- `python -m src.pipelines.analyze_company --ticker DEMO --offline-fixtures` 成功生成报告。
- 不配置任何外部 API key 时，offline demo 仍可运行。
- 端到端测试可在 CI 中执行。
- 真实 API 测试全部通过环境变量开关控制。

## 给执行助手的注意事项

- MVP 先追求闭环，不追求数据覆盖完美。
- 所有外部依赖失败都应降级，而不是让整个 demo 崩溃。
- 报告必须明确“仅供研究，不构成投资建议”。

