# 05 - Supply Chain Primary Agent Workflow

## 目标

把 Supply Chain Explorer 从 deterministic supplier discovery + LLM shadow 推进到 evidence-gated primary agent workflow。LLM planner 负责 query strategy、tool choice、candidate proposal；deterministic validators 负责 entity normalization、edge write gate、Sankey payload。

## 当前基线

已有：

- `SupplyChainExploreState`
- `SupplierCandidate`
- `llm_supplier_candidates`
- `llm_tool_traces`
- `SupplyChainSupplierDiscoveryStep(llm_shadow_mode=True)`
- graph builder、Sankey builder、evaluator

缺口：

- LLM candidate 还不是 primary source。
- edge write 仍只来自 deterministic search extraction。
- recursive expansion 未使用 agent subgoal loop。
- transcript / financial / graph context 尚未进入 supplier validation。

## Agent Flow

Supply Chain primary path：

```text
user goal
  -> AgentRunState(workflow_kind="supply_chain")
  -> product resolver / requirement decomposer
  -> planner creates supplier discovery subgoals per requirement
  -> LLM chooses search/fetch/transcript/financial/graph tools
  -> EvidenceCandidateNormalizer
  -> SupplierCandidate extractor
  -> entity resolver
  -> relation validator
  -> evidence-gated edge write
  -> Sankey payload
```

## Candidate Contract

LLM may propose:

- supplier
- customer
- partner
- component supplier
- infrastructure provider
- hypothesized relation

But confirmed graph edge requires:

- normalized entity id。
- accepted evidence id。
- relation validator pass。
- no self-loop。
- relation type not confused with customer/partner case study。

Snippet-only evidence can create `hypothesized` edge only.

## Tool Scopes

Supply Chain agent may use scope:

- `supply_chain`

Allowed tools:

- `web_search`
- `web_fetch`
- `search_and_fetch`
- `sec_fetch_filing`
- `transcript_lookup`
- `financial_metrics_lookup`
- `graph_query`
- `graph_path_search`

Not allowed:

- graph write。
- memory write。
- raw Cypher。
- low-level browser action。

## Migration Steps

### Step 1 - Query Strategy Subgoals

Planner creates subgoals per requirement:

- official company source query
- filing supplier/customer concentration query
- transcript commentary query
- financial metrics support query

### Step 2 - Candidate Extraction

Use unified evidence candidates plus LLM structured candidate proposal.

First implementation may keep `_supplier_from_text` as deterministic fallback.

### Step 3 - Evidence-Gated Edge Write

Only validator writes `SupplyChainEdge`:

```text
SupplierCandidate + accepted evidence + entity match
  -> relation validator
  -> SupplyChainEdge
```

### Step 4 - Recursive Expansion

For `max_depth > 1`, agent planner receives graph context and accepted edges, then creates next-level discovery subgoals.

### Step 5 - Review State

If candidate is plausible but evidence is weak:

- keep `llm_supplier_candidates`
- add human review item
- do not write confirmed edge

## Guardrails

- confirmed edge must have evidence ids。
- same supplier edge cannot be duplicated。
- private companies are allowed only if request permits。
- low-confidence source cannot upgrade relation to confirmed。
- graph write is never LLM-visible。

## 测试

新增：

```text
tests/supply_chain/test_supply_chain_agent_workflow.py
tests/supply_chain/test_supplier_candidate_validator.py
```

覆盖：

- LLM candidate with accepted evidence writes confirmed edge。
- snippet-only candidate becomes hypothesized。
- no evidence candidate is rejected or review-only。
- customer/partner relation not mislabeled as supplier。
- recursive expansion creates bounded subgoals。
- graph write tool not exposed in catalog。

## 验收

```bash
uv run pytest tests/supply_chain/test_supply_chain_agent_workflow.py tests/supply_chain/test_supplier_candidate_validator.py -q
uv run pytest tests/supply_chain -q
```
