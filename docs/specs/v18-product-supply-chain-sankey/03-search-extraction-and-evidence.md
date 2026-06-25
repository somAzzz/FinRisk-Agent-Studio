# 03 - Search、结构化抽取与 Evidence

## 目标

在 demo skeleton 稳定后，接入现有 `SearchRouter`、browser 和 LLM provider，将产品上游供应链发现从 fixture 升级为真实数据增强。

## 涉及文件

```text
src/tools/search_router.py
src/tools/providers/base.py
src/supply_chain/prompts.py
src/supply_chain/steps/requirement_decomposer.py
src/supply_chain/steps/supplier_discovery.py
src/supply_chain/steps/evidence_normalizer.py
tests/supply_chain/test_supplier_discovery.py
tests/supply_chain/test_evidence_normalizer.py
```

## Search Intent 扩展

在 search provider 类型中新增意图：

```text
product_supply_chain
supplier_discovery
component_supplier
cloud_dependency
datacenter_power
semiconductor_supply_chain
```

如果 `SearchIntent` 是 Literal，需要同步更新类型定义。

新增模板：

```python
INTENT_QUERY_TEMPLATES.update({
    "product_supply_chain": "{q} product supply chain suppliers upstream components",
    "supplier_discovery": "{q} suppliers companies official partnership evidence",
    "component_supplier": "{q} major suppliers manufacturers market share",
    "cloud_dependency": "{q} cloud provider datacenter infrastructure supplier",
    "datacenter_power": "{q} datacenter power electricity supplier energy contract",
    "semiconductor_supply_chain": "{q} semiconductor upstream foundry HBM lithography suppliers",
})
```

## 查询生成策略

输入：

```text
company = OpenAI
product = ChatGPT
component = GPU accelerator
```

查询候选：

```text
OpenAI ChatGPT GPU supplier NVIDIA evidence
OpenAI ChatGPT cloud provider Microsoft Azure evidence
OpenAI infrastructure supplier GPU NVIDIA Microsoft Azure
AI datacenter GPU supplier NVIDIA HBM memory supplier
Microsoft Azure AI datacenter GPU NVIDIA
```

对 CPU expansion：

```text
CPU upstream supply chain foundry lithography EDA wafer suppliers
AMD CPU foundry TSMC evidence
Intel CPU manufacturing foundry supply chain evidence
CPU lithography supplier ASML evidence
CPU EDA software Synopsys Cadence evidence
```

## Source 优先级

来源优先级：

1. Official company announcement。
2. SEC filing / annual report。
3. Earnings call transcript。
4. Investor relations presentation。
5. Reputable financial news。
6. Industry research / trade publication。
7. General web。

低质量来源：

- SEO 内容农场。
- 无来源博客。
- 论坛传言。
- 无日期网页。

低质量来源只能进入 `needs_review` 或 `hypothesized`。

## LLM 结构化抽取

LLM 输入：

- product context。
- component / requirement。
- search snippets 或 fetched page summaries。

LLM 输出：

```python
class ExtractedSupplierRelation(BaseModel):
    source_label: str
    target_company: str
    target_ticker: str | None
    component_or_service: str
    relation_type: str
    evidence_quote: str
    source_url: str | None
    confidence: float
    is_confirmed: bool
    uncertainty: str
```

要求：

- LLM 输出必须 `model_validate`。
- `source_url` 为空时不能 confirmed。
- `evidence_quote` 为空时不能 confirmed。
- `confidence < 0.5` 默认进入 `hypothesized`。

## Evidence Normalization

规则：

- 相同 URL + 相同 quote hash 去重。
- `evidence_id` 稳定生成：

```text
sc:web:{url_hash}
sc:fixture:{slug}
sc:filing:{ticker}:{accession}:{section}
```

- edge.evidence_ids 必须引用存在的 evidence。
- evidence metadata 记录：

```text
query
provider
rank
extraction_method
component
company
product
```

## Fallback 策略

任何外部失败都不应让 demo 崩溃：

```text
Search failure → cached search result
Cached miss → fixture edge marked needs_review
LLM failure → rule fallback
Browser failure → snippet evidence only
```

记录：

```text
fallback_events
warnings
guardrail_findings
```

## 测试要求

新增：

```text
tests/supply_chain/test_supplier_discovery.py
tests/supply_chain/test_evidence_normalizer.py
```

测试用例：

- SearchRouter intent 模板能正确拼接 query。
- mock provider 返回 NVIDIA snippet 后生成 supplier edge。
- 低质量来源不会生成 confirmed edge。
- 空 quote 不会生成 confirmed edge。
- URL + quote 去重有效。
- edge.evidence_ids 全部能在 evidence table 中找到。
- search failure 时 fallback 到 fixture。
- LLM invalid JSON 时使用 rule fallback。

验收命令：

```bash
uv run pytest tests/supply_chain/test_supplier_discovery.py tests/supply_chain/test_evidence_normalizer.py -q
```

