# 09 - Production Hardening Progress

## 本轮已完成

本文件记录 `08-production-hardening-and-real-data-plan.md` 的首轮工程化执行结果。

已完成：

- 将 `SupplyChainEvaluation.final_status` 从 workflow lifecycle status 改为质量 verdict：
  - `pass`
  - `needs_review`
  - `fail`
- `SupplyChainExploreState.status` 继续表达 workflow lifecycle：
  - `queued`
  - `running`
  - `completed`
  - `failed`
  - `needs_review`
- `/supply-chain/explore` 改为先创建 queued run，再通过 background task 执行 workflow。
- 测试环境可通过 `FINRISK_SKIP_BACKGROUND=1` 同步执行，保证 API tests 稳定。
- `SupplyChainExplorer` 接入主前端 `App.tsx`，新增应用级入口：
  - `Risk Intelligence`
  - `Product Supply Chain`
- 前端 `SupplyChainExplorer` 支持 queued/running 状态轮询后再拉取 Sankey。
- `RequirementDecomposerStep` 在 real mode 下不再返回空图，改为 rule-based requirement decomposition。
- `SupplierDiscoveryStep` 在 real mode 下接入 `SearchRouter`，能从搜索结果生成 evidence-backed supplier edge。
- `SearchRouter` 和 `SearchIntent` 增加 v18 供应链 intents：
  - `product_supply_chain`
  - `supplier_discovery`
  - `component_supplier`
  - `cloud_dependency`
  - `datacenter_power`
  - `semiconductor_supply_chain`
- 新增 `SupplyChainGraphWriter`，支持将 v18 nodes / edges / evidence 写入 Neo4j-compatible client。
- `GraphBuilderStep` 支持注入 graph client；无 client 时保留 in-memory fallback 并记录 fallback event。
- `src/graph/schema.cypher` 增加 v18 节点约束：
  - `Component`
  - `Service`
  - `Infrastructure`
  - `EnergySource`
  - `DataCenter`
- `SupplyChainTraceEvent` 增加 observability 字段：
  - `duration_ms`
  - `input_summary`
  - `output_summary`
  - `provider_calls`
  - `retry_count`
  - `cache_hit`
- `SupplierDiscoveryStep` 会记录 search provider call。
- 新增测试：
  - `tests/graph/test_supply_chain_writer.py`
  - `tests/supply_chain/test_observability.py`

## 当前验证结果

```bash
uv run pytest tests/supply_chain tests/api/test_supply_chain_api.py tests/graph/test_supply_chain_queries.py tests/graph/test_supply_chain_writer.py -q
# 51 passed

uv run pytest tests/supply_chain tests/api/test_supply_chain_api.py tests/graph/test_supply_chain_queries.py tests/graph/test_supply_chain_writer.py tests/tools/test_search_router.py -q
# 69 passed

uv run pytest -q
# 613 passed, 7 skipped

uv run ruff check src/workflows src/evaluation src/graph_reasoning src/reports src/api src/supply_chain src/graph
# All checks passed

cd frontend && npm test -- --run
# 31 passed

cd frontend && npm run build
# passed

uv run python -m src.supply_chain.workflow --company OpenAI --product ChatGPT --max-depth 3 --demo-mode
# completed, evaluation.final_status=pass
```

## 仍未完成的 Production 项

以下项目尚未完全完成，需要后续继续执行。

### LLM structured decomposer

当前 real mode 使用 rule-based decomposer。还需要：

- 增加 LLM structured output adapter。
- 输出 `RequirementDecomposition` Pydantic model。
- 对 invalid JSON / timeout 做 fallback。
- 记录 model、prompt version、latency、cost estimate。

### LLM / NLI supplier relation extractor

当前 supplier discovery 使用 SearchRouter + deterministic keyword extraction。还需要：

- 对 fetched page / search snippets 做 LLM relation extraction。
- 输出 `ExtractedSupplierRelation` Pydantic model。
- 区分 confirmed / hypothesized。
- 防止 LLM-only relation 进入 confirmed graph。

### Neo4j integration test

当前已实现 writer 和 mock tests。还需要：

```bash
RUN_NEO4J_INTEGRATION=1 uv run pytest tests/graph -m integration -q
```

并在真实 Neo4j 上验证：

- schema bootstrap。
- graph write。
- upstream path query。
- recursive expansion from stored graph。

### Persistent run store

当前 API 已支持 background task，但 run store 仍是 in-memory。还需要：

- SQLite 或 Redis-backed run store。
- run list / run replay。
- server restart 后恢复 run。

### Provider budget / retry policy

当前 trace 可记录 provider calls，但还未实现完整：

- max provider calls per run。
- retry with exponential backoff。
- timeout config。
- per-provider cache TTL。
- estimated cost budget。

### Full real acceptance

还需要在真实或 cached-real 模式跑：

```text
OpenAI + ChatGPT
→ SearchRouter discovery
→ evidence-backed Sankey
→ click CPU
→ recursive expansion
→ graph write/read
```

## 当前定位

本轮后，v18 状态从：

```text
fixture-driven demo skeleton
```

提升为：

```text
production-shaped engineering skeleton with real SearchRouter path,
background API execution, frontend entry, graph writer, and observability.
```

但还不是完整 production deployment。完整 production 仍需完成 LLM extraction、persistent store、Neo4j integration 和 provider budget controls。
