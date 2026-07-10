# Step 19 - Evidence-first Context & Guardrail Layer

## 目标

第 19 版在 v16 Quality Layer 和 v18 Product Supply Chain Explorer 的基础上，新增一个贯穿全项目的上下文与记忆质量层：

```text
Evidence-first Context & Guardrail Layer
```

它不是普通的 chat memory，也不是简单 vector memory。核心目标是让每一步 agent / workflow 在执行前都能获得：

- 最小但足够的上下文。
- 可追溯 evidence。
- 有效 graph path。
- 已知反证和失败经验。
- 明确标记的 evidence / inference / hypothesis / policy。
- 可审计的 selected / rejected context manifest。

## 与现有路线的关系

v16 解决：

- Guardrails 从最终验收变成横向质量层。
- Graph Reasoning 从普通 step 变成 graph query、path ranking、evidence binding、LLM explanation、visual validation 的组合。

v18 解决：

- 输入公司和产品。
- 发现上游供应链。
- 使用 Sankey 递归可视化。
- 逐步从 demo 走向工程化供应链探索。

v19 解决：

- 每一步使用什么上下文。
- 证据如何进入长期 memory。
- 哪些记忆不允许被使用。
- graph edge 如何被证据支撑。
- claim 如何绑定 memory item。
- stale / rejected / hypothesis 如何影响推理和报告。

## 核心原则

1. Evidence-first：长期记忆的核心是 evidence、claim、graph edge 和 workflow episode。
2. Context is a budget：每一步只拿当前任务需要的最小上下文。
3. Guardrails before generation：在 agent 生成前检查 ContextPack，而不是只在生成后补救。
4. Memory writes are gated：LLM 输出不能直接进入 active memory，必须先进入 candidate。
5. No agent prompt mutation：不允许 agent 自动修改 prompt、scoring formula、source policy 或 guardrail policy。
6. Procedural policy must be code-versioned：所有策略必须在代码或文档中版本化。
7. MVP first：先做可测试的 SQLite + keyword/entity selection，再逐步升级 embedding、Neo4j、feedback 和 production governance。

## 分阶段路线

### Phase 1：MVP Context Layer

目标：

- 新增 `src/memory`。
- 定义 `MemoryItem`、`ContextCandidate`、`ContextPack`。
- 实现 SQLite memory store。
- 实现基于 entity / keyword overlap 的 context selection。
- 实现基础 ContextPack guardrails。
- 优先接入 v18 Supply Chain 的测试数据。

不做：

- 向量数据库。
- 自动 prompt 改写。
- 复杂 semantic memory。
- 前端 Context Drawer。

### Phase 2：Evidence 与 Graph Memory 工程化

目标：

- 将 `Evidence`、`NormalizedSupplyChainEvidence`、SearchRouter 结果写入 Evidence Memory。
- 将 v18 supply chain edge 写入 Graph Memory。
- confirmed edge 必须有 evidence。
- hypothesis edge 只能进入 research context，不能作为 final fact。
- rejected memory 不允许进入 ContextPack。

### Phase 3：FinRisk Workflow 接入

目标：

- Filing risk extraction 写入 Evidence Memory。
- Market Explorer 使用 ContextPack 选择历史证据和反证。
- Graph Reasoner 只接收 validated graph path。
- Report Generator 的 claim 必须能追溯到 ContextPack。

### Phase 4：Episodic Memory 与 Human Feedback

目标：

- 保存 workflow episode。
- 保存 successful / failed queries。
- 保存 rejected claims 和 guardrail failures。
- 用户反馈可以把 memory item 标记为 rejected。
- negative memory 进入相关 step，避免重复犯错。

### Phase 5：Production Context Governance

目标：

- provider budget。
- per-source TTL。
- memory poisoning detection。
- observability dashboard。
- graph memory temporal versioning。
- optional embedding reranker。

## 完成定义

Phase 1 完成时，必须满足：

```bash
uv run pytest tests/memory tests/evaluation/test_context_guardrails.py -q
```

并且可以在代码中构造：

```python
context_pack = context_manager.build(
    run_id="run-demo",
    step_name="supplier_discovery",
    task="expand upstream suppliers",
    subject={"company": "OpenAI", "product": "ChatGPT", "node": "component:cpu"},
    intent="supplier_discovery",
    token_budget=4000,
)
```

输出必须包含：

- selected memory ids。
- rejected memory ids。
- stale / hypothesis warnings。
- estimated token count。
- context guardrail evaluation。

详细执行规格见：

```text
docs/specs/v19-context-guardrail-layer/
```
