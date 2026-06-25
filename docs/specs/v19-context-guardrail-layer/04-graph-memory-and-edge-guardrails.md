# 04 - Graph Memory 与 Edge Guardrails

## 目标

Graph Memory 管理长期关系，不只是 Sankey 展示。

## Edge 状态

```text
active
hypothesis
stale
rejected
superseded
```

规则：

- confirmed edge 必须有 evidence。
- hypothesis edge 可以无 evidence，但不能进入 final fact。
- rejected edge 不允许进入 ContextPack。
- stale edge 可以进入，但必须 warning。

## Supply Chain 用法

点击 Sankey 节点时：

```text
node click
→ query graph memory
→ retrieve edge evidence
→ build ContextPack
→ SearchRouter only fills gaps
→ write new candidate/active edges
```

## Guardrails

检查项：

- `edge_has_evidence`
- `edge_confidence_valid`
- `edge_type_valid`
- `node_type_valid`
- `no_duplicate_edge`
- `temporal_update_valid`
- `hypothesis_edge_flagged`

## 验收

- 无 evidence 的 confirmed edge 写入失败。
- hypothesis edge 写入成功但 final fact 不可用。
- rejected graph edge 不进入 ContextPack。
