# Chapter 6：Typed Toolsets 与权限边界

## 学习目标

理解如何把项目已有工具合同映射为 Pydantic AI typed tools，并通过 scope、risk level、结果 envelope 和执行时复核建立 capability isolation。

## 现实校正

生产代码已经实现这一章：

- `src/tools/contracts.py` 定义 `ProjectTool` 与 `ToolCatalog`；
- `src/tools/catalog.py` 组装 13 个项目工具；
- `src/ai/toolsets.py` 将 legacy-style catalog 映射为 `FunctionToolset`，再按 run 权限过滤；
- `tests/ai/test_toolsets.py` 验证 schema parity、可见性、执行时权限和 trace event。

因此练习目标不是修改生产实现，而是在 `tutorial_lab/ch06/` 独立重建一个最小版本，再与上述文件做设计评审。

## 当前工具面

| 领域 | 工具 | 风险 |
| --- | --- | --- |
| Web | `web_search`、`web_fetch`、`search_and_fetch` | read-only |
| Filing | `sec_list_filings`、`sec_fetch_filing` | read-only |
| Transcript | `transcript_lookup`、`management_snapshot_lookup` | read-only |
| Financial | `financial_metrics_lookup`、`xbrl_fact_lookup`、`financial_snapshot_lookup` | read-only |
| Graph | `graph_query`、`graph_path_search` | read-only |
| Browser | `browser_explore` | interactive |

每个工具还带 `scopes`、`evidence_kind` 和 `max_result_chars`。这些 metadata 不是装饰；它们必须参与权限、trace、evidence normalization 和 context 保护。

## 练习 6.1：画出双层合同

在写代码前，画出：

```text
ProjectTool metadata contract
  -> typed Pydantic tool schema
  -> ToolResultEnvelope
  -> ToolExecutionEvent
```

为每一层列出：输入、输出、负责的校验、失败表示、审计字段。

## 练习 6.2：最小 toolset adapter

在隔离目录实现最小 adapter，只支持三个 fake tools：

- 一个 read-only filing tool；
- 一个 read-only market tool；
- 一个 interactive browser tool。

接口合同由你实现：

```text
build_tutorial_toolset(catalog) -> FunctionToolset[TutorialDeps]
build_scoped_toolset(catalog) -> filtered/permission-aware toolset
```

要求：

- typed schema 与 `ProjectTool.parameters` 一致；
- `additionalProperties` 策略明确；
- tool metadata 被保留；
- sync callable 不阻塞 event loop；
- 所有返回值进入稳定 envelope；
- 异常成为可审计失败，不把 traceback 直接暴露给模型；
- 执行完成后记录 tool event。

不要复制 `src/ai/toolsets.py` 函数体。先根据合同实现，再比较。

## 练习 6.3：防御纵深

仅隐藏工具不够。测试两层权限：

1. model-visible filtering：不允许的工具不出现在 schema 中；
2. execution-time check：即使绕过可见性直接 call_tool，也必须拒绝。

解释为什么第二层不可省略：缓存的 schema、编程错误、恶意请求或未来 refactor 都可能绕开第一层。

## 练习 6.4：专业 scope 设计

从当前工具表设计四组 capability：

| Specialist | 应可见 | 不应可见 |
| --- | --- | --- |
| Filing | SEC、XBRL、financial snapshot | browser、任意 graph 写入 |
| Market | search/fetch、transcript、受控 browser | filing 全文抓取之外的无关工具 |
| Financial | metrics、XBRL、snapshot | browser、graph |
| Graph | query、path search | 任意写工具、web（除非另有明确任务） |

不要为了方便把所有工具都给 coordinator。

## 测试任务

- 所有 catalog tool 都有 typed schema 与 metadata parity；
- filing scope 看不到 market/browser/graph；
- interactive 默认隐藏；
- 直接调用被拒绝；
- success 与 failure 都记录 event；
- result chars 与 truncation 字段正确；
- 不可 JSON 序列化返回值有明确处理；
- duplicate tool name 在构建期失败。

测试使用 fake callable 与 `TestModel`，不访问 SEC、网络或 Neo4j。

## 对照评审

完成后再读：

- `src/ai/toolsets.py`
- `src/ai/deps.py`
- `tests/ai/test_toolsets.py`

写一页差异记录：你漏掉了哪些 edge cases？生产实现有哪些复杂度可以下沉或简化？哪些只是历史兼容，不能盲目照搬到新系统？

## DoD

- [ ] 最小 adapter 由你独立实现。
- [ ] schema、metadata、envelope 和 trace 合同均有测试。
- [ ] 可见性与执行时权限双重生效。
- [ ] specialist scope 不暴露无关工具。
- [ ] 生产 `src/ai/toolsets.py` 未被练习代码破坏。
- [ ] 能解释为什么 Toolset 比“一个 Agent 拿所有工具”更安全。

