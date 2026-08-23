# Pydantic AI PAI-4 验收记录

- 验收日期：2026-08-23
- 状态：typed output contracts passed，primary 生产解析边界已接线

## 已交付

- Supply Chain relation batch Agent：confirmed edge 强制 URL 与 quote；
- Filing risk extraction Agent：空结果必须进入 review；
- Planner Agent：未知 scope/tool 触发有限 `ModelRetry`；
- Graph interpretation Agent：path 与 evidence provenance 强校验；
- Report generation Agent：每个 top risk 必须映射 normalized evidence；
- generic entity/relation/claim/evidence extraction Agent。
- `/agent-runs` primary 使用 `PydanticAIPlanner` 生成并校验 planner decision，
  非法 scope/tool 或 pending subgoal 不匹配时进入有限重试，再由既有确定性
  planner 承担受控 fallback；
- filing risk extractor 在 `pydantic_ai_primary` 下使用
  `PydanticAIFilingExtractionClient`，逐 chunk 输出 typed batch 后再投影到 canonical
  `ChunkValidation`/`LLMCall`；
- supply-chain relation extraction 在 primary 下使用
  `PydanticAISupplierRelationClient`，不再由生产分支手工剥离 fenced JSON；
- Graph interpretation 与 Report generation 当前生产步骤本身是确定性计算，不存在
  LLM JSON 解析替换点，因此保留 typed Agent 合同但不强行引入新的模型调用。

现有 deterministic fallback 和 legacy JSON helpers 暂时保留，删除清单为空；
它们仍是 shadow/回滚路径，只有 PAI-7 观察期结束后才允许移除。

## 验证结果

```text
pytest tests/agents/test_extraction_agent.py \
  tests/supply_chain/test_llm_json.py \
  tests/supply_chain/test_llm_supplier_discovery.py \
  tests/agents/test_agent_planner_v21.py \
  tests/graph_reasoning tests/workflows/test_guardrails.py \
  tests/pipelines/test_generate_report.py tests/reports \
  tests/ai/test_structured_agents.py \
  tests/ai/test_structured_clients.py \
  tests/ai/test_planner_adapter.py -q
80 passed
```
