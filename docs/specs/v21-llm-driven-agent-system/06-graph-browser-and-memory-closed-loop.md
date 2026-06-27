# 06 - Graph, Browser, and Memory Closed Loop

## 目标

让 graph read、browser explore、context/memory 进入 agent reasoning loop，同时保持写边界。

V21 中这些能力的定位：

- graph：帮助 agent 发现二阶路径、供应链暴露、政策传导。
- browser：在静态 fetch 失败或页面需要交互时作为高层探索工具。
- memory/context：为 planner 提供历史 evidence、feedback、entity context。

## 当前基线

已有：

- `graph_query`
- `graph_path_search`
- `browser_explore`
- V19 memory/context guardrail specs
- graph write gates

缺口：

- graph/browser 输出没有统一进入 `EvidenceCandidate`。
- memory/context 还没有作为 planner input。
- graph path insight 还没有 agent-level follow-up loop。

## Graph Closed Loop

Graph tools 返回：

- paths
- nodes
- edges
- evidence ids
- confidence
- path text

Normalizer 生成 `EvidenceCandidate(kind="graph_path")`。

Planner 可基于 graph candidate 决定：

- 补 web evidence。
- 补 SEC filing。
- 补 transcript。
- 进入 graph insight validator。
- 标记 uncertainty。

Graph write 仍由 validator 控制，LLM 不直接写图。

## Browser Closed Loop

`browser_explore` 是高层工具，只接受：

- `goal`
- `initial_urls`
- `max_steps`

不暴露：

- click
- type
- scroll
- selector
- arbitrary JS

Browser findings 进入 `EvidenceCandidate(kind="browser")`，再由 source quality / grounding 决定是否 accepted。

## Memory / Context Closed Loop

V21 只做 read-first memory integration：

- Planner 可读取 ContextPack。
- Evidence normalizer 可读取 known entities / prior evidence ids。
- Human review feedback 可作为 future context。

不做：

- LLM 直接写 memory。
- LLM 修改 guardrail policy。
- LLM 删除 historical evidence。

Memory 写入必须由 workflow 或 review action 触发。

## Planner Inputs

每次 planner decision 应包含：

- current accepted evidence summary。
- unresolved uncertainty。
- candidate graph paths。
- recent similar runs from memory。
- human feedback if available。

## Guardrails

- graph path without evidence ids 只能作为 hypothesis。
- browser result from low-quality source 默认 `needs_review`。
- memory context 不能覆盖当前证据。
- old memory evidence 必须标注 collected_at。
- planner 必须区分 current evidence 和 historical context。

## 测试

新增：

```text
tests/agents/test_graph_browser_memory_loop.py
tests/evidence/test_graph_browser_candidates.py
```

覆盖：

- graph path event -> graph_path candidate。
- browser finding -> browser candidate。
- raw Cypher 不在 tool schema。
- click/type/scroll 不在 browser tool schema。
- memory context 进入 planner input。
- memory context 不直接进入 accepted evidence。

## 验收

```bash
uv run pytest tests/agents/test_graph_browser_memory_loop.py tests/evidence/test_graph_browser_candidates.py -q
```
