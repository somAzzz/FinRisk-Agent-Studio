# Chapter 7：Specialist Agents 与 Delegation

## 学习目标

设计具有窄工具面、typed evidence output 和共享预算的专业研究 Agent，并区分程序化 handoff 与模型驱动 delegation。

## 哪些组件不应 Agent 化

先阅读并确认：

- `src/agents/risk_agent.py`：确定性风险聚合；
- `src/agents/critic.py`：规则式清理；
- `src/agents/report_agent.py`：确定性 Markdown 组装；
- `src/graph_reasoning/`：路径检索、评分、绑定与验证；
- `src/evaluation/`：证据、grounding、安全与 workflow validators。

这些组件的价值来自可审计规则，不应为了“多 Agent”改成 LLM Agent。

适合 LLM specialist 的任务是：从 filing 发现材料、研究当前市场信息、解释已经验证的 graph path。

## 当前可参考实现

- `src/ai/agents/research.py`：现有 typed market research output；
- `src/ai/agents/structured.py`：filing/supply-chain typed boundaries；
- `src/ai/runtime_adapter.py`：把 Agent run 映射回 workflow contract；
- `src/ai/deps.py`：共享 permissions、budget、services；
- `tests/ai/test_research_agent.py`：grounding contract 测试。

本章仍建议在 `tutorial_lab/ch07/` 独立实现，不直接改生产 Agent。

## 练习 7.1：设计 specialist output

为研究结果设计 typed schema，至少表达：

- finding 类型；
- statement；
- evidence IDs；
- confidence；
- uncertainty；
- missing information；
- status（例如 completed / needs_review）。

必须满足：

- 禁止额外字段；
- material finding 至少一个 evidence ID；
- 无 evidence 时不能标记 completed；
- evidence ID 在单次结果中不重复；
- confidence 在 0–1；
- uncertainty 不是用空字符串敷衍。

思考：这些条件哪些属于 schema/model validator，哪些必须查询 evidence store 后才能验证？

## 练习 7.2：三个 specialists

由你实现最小版本：

### Filing Researcher

- 只看 filing 与 financial tools；
- 优先 primary SEC evidence；
- 区分披露事实、解释和不确定性；
- 不做投资建议。

### Market Researcher

- 只看 search/fetch/transcript 和明确允许的 browser；
- snippet 不是最终证据；必要时 fetch source；
- 记录来源质量和时点；
- 无可用来源时 needs_review。

### Graph Interpreter

- 只解释 tool 返回的 verified paths；
- 绝不创造 edge；
- 缺少 path 记为 missing information；
- 输出中的 evidence ID 必须对应 path/evidence payload。

每个 Agent 都应使用 Chapter 6 的窄 toolset，而不是同一全量 catalog。

## 练习 7.3：first-line output validator

实现可确定检查：finding 是否至少带一个非空 evidence ID。

不要在这个 validator 中假装完成：

- evidence ID 是否真实存在；
- quote 是否支持 claim；
- source 是否足够高质量；
- 多来源是否独立。

这些需要现有 `EvidenceCandidateNormalizer`、claim grounding 与 quality layer。

## 练习 7.4：Core delegation

先不使用 Harness。设计一个 coordinator，把 specialist Agent 暴露为窄 delegation tools。

行为合同：

- filing 问题只调用 Filing Researcher；
- 当前市场问题调用 Market Researcher；
- supply-chain 路径解释调用 Graph Interpreter；
- 混合任务可调用多个 specialist；
- child 使用 self-contained task，而不是“分析那个”；
- parent/child usage 合并或明确归集；
- 每个 child 有独立 request/tool/token 限制；
- child failure 成为结构化失败，不能让整条 trace 消失。

这与 Chapter 4 的差异：Chapter 4 由 Python 固定调用顺序；本章允许 coordinator 模型选择 specialist。

## 练习 7.5：接回确定性 pipeline

specialist output 不能直接成为 final report。目标链路：

```text
Specialist typed output
  -> evidence normalization
  -> evidence existence / source checks
  -> claim creation and binding
  -> deterministic critic and risk logic
  -> graph validation
  -> quality gate / human review
  -> deterministic report
```

在隔离 lab 中可以用 fake normalizer 模拟，但需要为每一个边界定义输入输出。

## 测试任务

- 每个 specialist 只看到允许工具；
- 完成状态必须有 evidence；
- duplicate evidence IDs 被拒绝；
- filing-only 问题不调用 market/graph；
- 混合任务的 usage 不越界；
- child timeout/failure 被记录；
- graph interpreter 不把 empty path 转成否定事实；
- specialist 结果不会绕过 deterministic quality layer。

使用 `TestModel` 检查 schema/tool exposure，使用 `FunctionModel` 精确控制 delegation 路径。不要用 TestModel 衡量金融研究能力。

## DoD

- [ ] 三个 specialist 都有窄工具面。
- [ ] 输出是 typed findings，不是自由 Markdown。
- [ ] evidence 引用是 mandatory first-line contract。
- [ ] parent 与 child usage 可追踪且受限。
- [ ] graph edge 不由 LLM 创造。
- [ ] 确定性 Risk/Critic/Report/validators 未被替换。
- [ ] 能解释 programmatic handoff 与 Agent delegation 的区别。

## 面试题

为什么不让整个 FinRisk pipeline autonomous？

你的回答应包含：探索和解释适合 Agent；证据确认、评分、权限与发布必须保持确定性、可审计，并在高风险金融场景保留人工复核。

