# 05 - Supply Chain Workflow Migration

## 目标

把 v18 Product Supply Chain Explorer 中的供应商发现、证据补全、二阶扩展迁移到 LLM-driven tool loop。

LLM 负责：

- 选择 search/fetch/transcript/financial metrics。
- 生成候选 query。
- 判断是否需要更多证据。
- 提出候选 supplier/customer/component。

确定性代码负责：

- entity normalization。
- supplier edge construction。
- evidence validation。
- graph write。
- Sankey payload generation。

## 现状

`SupplyChainSupplierDiscoveryStep` 当前使用：

```python
response = router.search(query=query, intent=intent)
_supplier_from_text(...)
```

这是可控的，但 discovery 能力较窄：

- query 模板固定。
- 只靠 search snippet。
- 不 fetch 深层页面。
- 不结合 transcript/financial metrics。

## LLM tool scope

Supply chain scope 允许：

- `web_search`
- `web_fetch`
- `search_and_fetch`
- `transcript_lookup`
- `financial_metrics_lookup`
- `sec_fetch_filing`
- `graph_query`

不允许：

- `graph_write`
- `memory_write`
- browser low-level actions。

## Candidate model

新增或复用 schema：

```python
class SupplierCandidate(BaseModel):
    supplier_name: str
    ticker: str | None
    relation_type: Literal["supplied_by", "customer_of", "partner", "hypothesized"]
    product_or_service: str | None
    evidence_ids: list[str]
    confidence: float
    uncertainty: str | None
```

LLM final answer 可以提出 candidates，但写入 state 前必须经过：

```text
candidate
  → entity resolver
  → evidence binder
  → relation validator
  → graph/write gate
```

## Query strategy

LLM prompt 应鼓励多源验证：

1. Company + product + requirement + supplier。
2. Company + product + customer/supplier official。
3. Filing text for supplier/customer concentration。
4. Transcript Q&A for supply bottlenecks and demand signal。
5. Financial metrics for capex/revenue confirmation。

## Migration steps

### Step 1 - LLM query generation only

LLM 只生成 search query list。SearchRouter 仍由 deterministic step 执行。

### Step 2 - LLM tool loop shadow mode

LLMToolAgentRuntime 可调用 search/fetch，但结果只进入 trace。

### Step 3 - Evidence candidate mode

LLM tool results 转为 evidence candidates，进入 existing `_add_supplier_edges` 前的候选池。

### Step 4 - Candidate extraction mode

LLM 输出 `SupplierCandidate`，但 deterministic validator 决定是否写入 edge。

### Step 5 - Recursive expansion mode

对于 depth > 1 的节点，LLM 根据已有 graph context 选择下一步工具。

## Guardrails

- confirmed edge 必须有至少一个 evidence quote/url。
- snippet-only evidence 默认只能生成 `hypothesized` edge。
- LLM 不能把“客户案例/合作伙伴”直接当供应商，必须标 relation uncertainty。
- 对关键供应链结论优先要求 source diversity。
- graph write 只发生在 validator 通过后。

## 测试

新增：

```text
tests/supply_chain/test_llm_supplier_discovery.py
```

覆盖：

- LLM query generation 不写 edge。
- LLM tool results 进入 candidate pool。
- 没有 evidence 的 confirmed edge 被降级或拒绝。
- transcript evidence 可以支撑 supplier/customer relation。
- graph write gate 不暴露给 LLM catalog。

## 验收

```bash
uv run pytest tests/supply_chain/test_llm_supplier_discovery.py tests/supply_chain -q
```
