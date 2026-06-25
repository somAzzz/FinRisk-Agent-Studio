# Step 07 - 年报、电话会议和网页的实体关系抽取 Pipeline

## 目标

实现统一 extraction pipeline，从 filing、transcript 和网页 evidence 中抽取实体、关系和初步 claim。

这是供应链图谱和机会发现的输入层。

## 需要新增或修改的文件

新增：

```text
src/agents/filing_agent.py
src/agents/transcript_agent.py
src/agents/web_agent.py
src/agents/extraction_agent.py
src/pipelines/__init__.py
src/pipelines/extract_from_filing.py
src/pipelines/extract_from_transcript.py
src/pipelines/extract_from_web.py
tests/agents/test_extraction_agent.py
tests/pipelines/test_extract_from_filing.py
tests/pipelines/test_extract_from_transcript.py
```

修改：

```text
src/llm/sglang_client.py
```

## 抽取对象

第一阶段重点抽取：

实体：

- company
- product
- segment
- customer
- supplier
- competitor
- country
- region
- commodity
- policy
- risk
- opportunity

关系：

- supplies_to
- buys_from
- customer_of
- competitor_of
- sells_product
- has_segment
- depends_on
- exposed_to
- mentions_risk
- benefits_from
- impacted_by

Claim：

- supply_chain
- risk
- opportunity
- policy_exposure
- geopolitical_exposure
- sentiment

## 输入切分

Filing section 可能很长，必须 chunk：

```python
class TextChunk(BaseModel):
    source_id: str
    source_type: str
    section: str | None
    text: str
    char_start: int
    char_end: int
```

建议 chunk 策略：

- 按 section 分。
- 每个 chunk 约 4000-8000 字符。
- 保留 overlap 300-500 字符。
- 不在本步骤做 token 精确切分，后续可优化。

## LLM Structured Output

新增输出 schema：

```python
class ExtractionResult(BaseModel):
    entities: list[Entity]
    relations: list[Relation]
    claims: list[Claim]
    evidence: list[Evidence]
    warnings: list[str] = Field(default_factory=list)
```

LLM 提示词要求：

- 只抽取文本中明确支持的信息。
- 每个 entity/relation/claim 必须引用 evidence quote。
- 不要猜测未出现的供应商或客户。
- 不确定时降低 confidence。
- 区分“公司披露的风险”和“实际发生的事件”。

## Filing Agent

职责：

- 输入 `FilingRecord`。
- 优先处理：
  - `section_1`
  - `section_1A`
  - `section_7`
  - `section_7A`
  - `full_text` fallback
- 输出 entities、relations、claims、evidence。

特殊规则：

- Item 1 更适合抽供应链和产品。
- Item 1A 更适合抽风险。
- MD&A 更适合抽需求、margin、capex、供应链变化。

## Transcript Agent

职责：

- 输入 `Transcript`。
- 分 prepared remarks 和 Q&A。
- 抽取：
  - demand signal
  - margin pressure
  - supply bottleneck
  - capex plan
  - customer comments
  - policy comments
  - geopolitical comments

特殊规则：

- Analyst question 不能当作公司事实，除非 management answer 确认。
- Q&A 中的回避、模糊、反复强调要保留为 sentiment evidence。

## Web Agent

职责：

- 输入 `WebFetchResult` 或 browser findings。
- 抽取：
  - contracts
  - partnerships
  - suppliers/customers
  - recent events
  - policy/news impact

特殊规则：

- 新闻来源必须带 URL。
- 二手来源 confidence 默认低于 SEC filing 和公司 transcript。

## Entity Resolution 初版

本步骤实现简单归一化：

- 小写
- 去掉 Inc., Corp., Ltd., Corporation 等后缀
- ticker/CIK 完全匹配优先
- aliases 合并

新增：

```text
src/data/entity_resolver.py
tests/data/test_entity_resolver.py
```

## 测试策略

使用 fake LLM client 返回固定 structured output。

测试覆盖：

- chunk 生成。
- Filing Agent 处理 section。
- Transcript Agent 区分 prepared remarks 和 Q&A。
- evidence quote 被保留。
- relation 没有 evidence 时被拒绝或降级。
- entity resolver 合并简单公司别名。

## 验收标准

- 可以从一个 mock FilingRecord 抽出 Entity/Relation/Claim。
- 可以从一个 mock Transcript 抽出 sentiment/supply_chain claim。
- 所有输出都是 Step 01 的 schema。
- 每个 claim 至少有一条 evidence。

## 给执行助手的注意事项

- 不要追求一次抽取完美，先保证结构和证据链正确。
- 不要让 LLM 输出裸 dict，必须 parse 到 Pydantic。
- Prompt 应放在代码中清晰可测试的位置，后续可迁移到模板文件。

