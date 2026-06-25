# V18 Specs - Product Supply Chain Explorer 与 Sankey 递归发现

## 目标

本目录细化：

```text
docs/implementation-plan/18-product-supply-chain-sankey-roadmap.md
```

第 18 版目标：

> 输入公司与产品，发现该产品的主要上游供应链公司、产品、服务、基础设施和资源，用 Sankey 图展示依赖流向，并支持点击任意上游节点后递归展开。

第一版稳定 demo：

```text
Company: OpenAI
Product: ChatGPT
```

必须展示：

```text
ChatGPT
→ Cloud service
→ GPU
→ CPU
→ HBM memory
→ Networking
→ Data center power
```

点击 `CPU` 后必须可继续展开：

```text
CPU
→ Intel / AMD
→ Foundry
→ TSMC / Intel Foundry
→ Lithography
→ ASML
```

## 执行顺序

1. `01-models-and-fixtures.md`
2. `02-workflow-and-recursive-expansion.md`
3. `03-search-extraction-and-evidence.md`
4. `04-graph-storage-and-sankey-payload.md`
5. `05-api-and-frontend-sankey.md`
6. `06-testing-and-acceptance.md`
7. `08-production-hardening-and-real-data-plan.md`
8. `09-production-hardening-progress.md`

## 与现有系统关系

复用：

- `src/tools/search_router.py`
- `src/browser/explorer.py`
- `src/llm/*`
- `src/schemas/evidence.py`
- `src/graph/writer.py`
- `src/graph/queries.py`
- `src/evaluation/*`
- `src/api/run_store.py`
- `frontend` React app shell

新增：

- `src/supply_chain/*`
- `src/api/supply_chain.py`
- `src/graph/supply_chain_queries.py`
- `frontend/src/components/SupplyChain*.tsx`
- `tests/supply_chain/*`

## 全局工程要求

- 第一版必须支持完全离线 `demo_mode`。
- 第一版不要求真实 Neo4j、真实 browser、真实 LLM。
- 所有外部数据能力必须有 cached fallback。
- 所有 confirmed edge 必须绑定 evidence。
- 没有 evidence 的关系只能标记为 `hypothesized` 或 `needs_review`。
- Sankey payload 必须 acyclic。
- 边宽第一版表示 `importance` 或 `confidence_weight`，不得伪装成真实采购金额。
- 前端点击节点必须可以发起 recursive expansion。

## 全局验收命令

```bash
uv run pytest tests/supply_chain tests/api -q
uv run pytest tests/workflows tests/evaluation tests/graph_reasoning -q
cd frontend && npm test -- --run
cd frontend && npm run build
```

如果对应目录尚未创建，实现本 spec 时同步创建。

## Demo 与 Production 的边界

`07-completion-summary.md` 记录的是 v18 demo acceptance：fixture-driven workflow、Sankey payload、API、前端组件和测试已经跑通。

如果目标是“真正工程化项目”，必须继续执行：

```text
docs/specs/v18-product-supply-chain-sankey/08-production-hardening-and-real-data-plan.md
```

该文件定义从 demo skeleton 升级到 production-grade product supply chain intelligence system 的修正方案。
