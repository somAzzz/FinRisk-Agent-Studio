# v19 Context Guardrail Layer Specs

## 目标

本目录细化 Step 19 的执行方案：构建 Evidence-first Context & Guardrail Layer。

第 19 版不替代 v16 / v18，而是作为共享质量层服务：

- FinRisk Workflow。
- Product Supply Chain Explorer。
- SearchRouter / Browser / LLM evidence acquisition。
- Neo4j graph reasoning。
- Report generation。

## 文件导航

```text
01-memory-models-and-lifecycle.md
02-context-pack-builder.md
03-evidence-memory-store.md
04-graph-memory-and-edge-guardrails.md
05-global-context-guardrails.md
06-workflow-integration-finrisk-and-supply-chain.md
07-episodic-memory-and-feedback.md
08-testing-and-acceptance.md
09-productionization-roadmap.md
10-phase-2-evidence-graph-memory-progress.md
```

## MVP 边界

MVP 做：

- Pydantic memory models。
- SQLite memory store。
- ContextPack builder。
- keyword / entity based ranking。
- context guardrails。
- tests。

MVP 不做：

- vector database。
- prompt 自动改写。
- full semantic memory。
- frontend Context Drawer。
- production memory governance。

## 执行顺序

```text
1. models
2. store
3. context ranker
4. context manager
5. guardrails
6. tests
7. v18 workflow integration
8. FinRisk integration
```
