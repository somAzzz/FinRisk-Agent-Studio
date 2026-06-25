# V16 Spec 02 - Claim Grounding 与 Source Quality

## 目标

让系统能回答：

- 每个 claim 有没有 evidence？
- evidence 是否真的支持 claim？
- source 是否可信、是否新鲜、是否重复？

这是 FinRisk Agent Studio 区别普通报告生成器的核心能力。

## 新增或修改文件

```text
src/evaluation/validators/claim_grounding_validator.py
src/evaluation/validators/source_quality_validator.py
src/evaluation/metrics/source_diversity.py
src/evaluation/metrics/hallucination_risk.py
tests/evaluation/test_claim_grounding_validator.py
tests/evaluation/test_source_quality_validator.py
```

## Claim schema

在 `src/schemas/finrisk.py` 或等价 schema 文件中新增：

```python
class Claim(BaseModel):
    claim_id: str
    text: str
    claim_type: Literal["evidence", "inference", "hypothesis"]
    supporting_evidence_ids: list[str]
    confidence: float = Field(ge=0, le=1)
```

要求：

- final report 中的重要判断必须变成 Claim。
- markdown 只是 Claim 的渲染结果。
- `hypothesis` 可以 evidence 弱一些，但必须明确标记。

## Claim grounding 三层

### Layer 1：规则检查

检查：

- `supporting_evidence_ids` 非空。
- evidence id 在 state.normalized_evidence 中存在。
- claim_type 合法。
- confidence 合法。

输出 finding：

- missing evidence -> ERROR/BLOCKER
- evidence id 不存在 -> BLOCKER

### Layer 2：Lexical overlap v1

第一版不要求 embedding 模型。先实现 lexical overlap：

```text
claim_tokens ∩ evidence_tokens / claim_tokens
```

规则：

- overlap >= 0.25 -> likely grounded
- 0.10 <= overlap < 0.25 -> needs_review
- overlap < 0.10 -> unsupported warning

后续可替换为 embedding similarity。

### Layer 3：Optional LLM / NLI judge

设计接口但第一版可不启用：

```python
class ClaimGroundingJudgement(BaseModel):
    claim_id: str
    verdict: Literal["supported", "partially_supported", "unsupported", "contradicted"]
    explanation: str
    missing_evidence: str | None = None
```

要求：

- LLM judge 输出只作为一个 signal。
- 不能单独决定最终 pass/fail。
- demo mode 默认关闭 LLM judge。

## SourceQuality schema

新增：

```python
class SourceQuality(BaseModel):
    source_url: str
    source_type: Literal[
        "filing",
        "regulatory",
        "company",
        "financial_news",
        "general_news",
        "blog",
        "unknown",
    ]
    credibility_score: float = Field(ge=0, le=1)
    freshness_score: float = Field(ge=0, le=1)
    relevance_score: float = Field(ge=0, le=1)
    is_primary_source: bool
```

## Source scoring v1

建议默认分：

```text
SEC filing / official filing: 1.0
company IR / official report: 0.9
Reuters / CNBC / WSJ / Bloomberg: 0.8
industry report: 0.7
general news: 0.6
blog / unknown commentary: 0.4
unknown source: 0.2
```

freshness：

- filing evidence 可固定 0.7。
- 30 天内 web evidence：1.0。
- 180 天内：0.7。
- 1 年内：0.5。
- 超过 1 年：0.3。

## Source diversity

简单指标：

```python
source_diversity = unique_source_domains / max(1, evidence_count)
```

增强指标：

```text
filing + company + news + regulatory = high
only same domain repeated = low
```

Guardrail：

- only one source domain and evidence_count > 3 -> warning。
- no primary source -> needs_review。

## Evidence genericness check

过滤空洞证据：

```text
"company faces risks"
"market conditions may affect business"
"there are uncertainties"
```

规则：

- quote/summary 少于 20 字符 -> warning/error。
- 包含过多 generic phrase 且无具体实体 -> warning。

## 前端输出需求

本 spec 需要为前端 Evaluation tab 提供：

- Claim-Evidence Matrix。
- Source Quality Panel。
- Unsupported claim list。
- Low-quality source warnings。

## 验收测试

新增：

```text
tests/evaluation/test_claim_grounding_validator.py
tests/evaluation/test_source_quality_validator.py
```

测试点：

- claim 无 evidence -> blocker。
- claim evidence id 不存在 -> blocker。
- lexical overlap 高 -> pass。
- lexical overlap 低 -> needs_review。
- SEC filing source quality = high。
- unknown blog source quality = low。
- duplicate source domain -> warning。
- no primary source -> needs_review。

## 验收命令

```bash
uv run pytest tests/evaluation/test_claim_grounding_validator.py -q
uv run pytest tests/evaluation/test_source_quality_validator.py -q
```

