# Pydantic AI PAI-5 验收记录

- 验收日期：2026-08-23
- 状态：顺序版通过；并行生产接线暂不启用

## 已交付

- FinRisk 九步 Pydantic Graph，一比一复用 canonical workflow state/steps；
- Supply Chain 九步 Pydantic Graph，一比一复用 store 与 state contract；
- FinRisk critical/non-critical quality policy 映射；
- graph result 到既有 public state 的直接投影；
- demo workflow sequential parity tests；
- stable、idempotent、失败分支不丢成功结果的 reducer。
- 可执行的 `validate_parallel_group` 准入策略：共享写、读写依赖或共享 trace 写入
  均 fail closed；只有独立输入快照才允许进入并行组。

当前 Market Research 依赖 Filing Risk 输出，Supply Chain 节点又共享递归图状态，
尚不存在无需复制 mutable state 的安全生产 fan-out。因此本阶段没有为了并行而
改变业务依赖；准入测试明确拒绝当前 `filing_risk -> market_explorer` 组合，并接受
独立的 filing-fetch/transcript-fetch 快照示例。parallel reducer 已验证，待形成
真正独立的输入快照并取得 wall-time 改进数据后再启用。旧顺序 orchestrator 继续
作为回滚路径。

## 验证结果

```text
pytest tests/ai/graphs -q
7 passed

pytest tests/ai/graphs/test_finrisk_graph.py \
  tests/ai/graphs/test_supply_chain_graph.py \
  tests/workflows/test_workflow_contract.py \
  tests/workflows/test_v16_quality_gated_orchestrator.py \
  tests/supply_chain/test_workflow_demo.py \
  tests/supply_chain/test_recursive_expansion.py -q
39 passed
```
