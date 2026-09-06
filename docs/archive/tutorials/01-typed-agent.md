# Chapter 1：用 Typed Agents 固定模型输出边界

> 当前实现导读。FinRisk 不用一个万能 JSON schema 覆盖所有任务，而是让每个模型任务返回
> 下游真正消费的 Pydantic model。

## 本章结果

完成本章后，你应能解释：

- public workflow state 与 Agent output 为什么是两种不同粒度的合同；
- filing、market、planner 和 supply-chain Agents 分别返回什么；
- typed client 如何把 `result.output` 接回既有领域协议；
- 哪些事实不能只靠 Pydantic schema 证明。

## 当前文件地图

| 文件 | 当前职责 |
| --- | --- |
| `src/schemas/finrisk.py` | FinRisk workflow、API、报告共同使用的 typed schemas |
| `src/schemas/{entities,relations,claims,evidence}.py` | 通用抽取领域对象 |
| `src/supply_chain/llm_models.py` | requirements、supplier proposal 和 node profile outputs |
| `src/supply_chain/llm_extraction.py` | supplier relation typed output |
| `src/ai/agents/research.py` | source-backed market research output 与 Agent builder |
| `src/ai/agents/structured.py` | 各专用 structured Agent builders 和局部 validators |
| `src/ai/structured_clients.py` | 把 typed Agents 接到现有业务调用协议 |
| `src/agents/extraction_agent.py` | source-agnostic `ExtractionResult` 与 typed client Protocol |

## 1.1：先区分三种模型

### 请求与工作流状态

`FinRiskRequest`、`FinRiskWorkflowState` 是产品级合同。它们需要跨越 workflow、API、store 和
frontend，因此字段较多、生命周期较长。

### Agent output

Agent output 是一次模型任务的最小合同。例如 filing Agent 只返回 risks、warnings 和
`needs_review`，而不是整个 workflow state。

### 确定性领域结果

`RiskScore`、report、validated graph edge 等结果由 Python 规则产生。它们可以使用 Pydantic
model，但不是模型生成的 Agent output。

不要因为三者都使用 Pydantic，就把它们混成一个巨型 schema。

## 1.2：当前专用 Agent outputs

| 模型任务 | Typed output | 关键局部规则 |
| --- | --- | --- |
| filing risk extraction | `FilingRiskExtractionOutput` | 空 risks 必须 `needs_review=True` |
| market research | `ResearchAgentOutput` | 无 evidence 不得 completed；source ID 去重 |
| supplier relation | `SupplierRelationBatch` | confirmed relation 必须有 URL 和 quote |
| requirement decomposition | `RequirementDecomposition` | 复用 supply-chain 领域 schema |
| supplier proposal | `SupplierProposalBatch` | 候选是 hypothesis，不自动 confirmed |
| node profile | `NodeProfileBatch` | 只消费提供的 graph context |
| generic extraction | `ExtractionResult` | entities/relations/claims/evidence 分开 |
| planner | `AgentDecision` | stop reason、scope 和 tool selection 有类型约束 |

所有这些 output 都由 `Agent(..., output_type=..., deps_type=...)` 直接声明。调用方读取
`result.output`，不从 Markdown code fence 抠 JSON，也不替换引号或括号尝试“修复”模型文本。

## 1.3：最完整示例——filing risk extraction

真实调用链：

```text
FilingRiskExtractorStep
  -> 取得 filing / Item 1A 文本
  -> chunk_text(...)
  -> PydanticAIFilingExtractionClient.extract_risks_chunked(...)
  -> build_filing_extraction_agent(model)
  -> Agent.run(prompt, deps)
  -> FilingRiskExtractionOutput
  -> ExtractedRisk + ChunkValidation + LLMCall
  -> FinRiskWorkflowState
```

`TextChunk` 保留 source、section、`char_start` 和 `char_end`。每个 chunk 创建独立 run ID；
成功后记录 structured response、messages、tokens、latency 和 validation row。

这比“让模型返回风险 JSON”多出的价值是：结果可以回到源文档位置，并能区分模型输出、校验状态
和 workflow 接受状态。

## 1.4：Market Research 的 grounding 最低合同

每条 `ResearchEvidence` 包含：

```text
source_id
source_url
evidence_kind
quote_or_summary
claim
confidence
```

`ResearchAgentOutput` validator 能证明“没有任何 evidence 的回答不能标 completed”，但不能证明：

- URL 内容真实存在；
- quote 确实来自该 URL；
- quote 逻辑上支持 claim；
- 两条来源相互独立；
- confidence 等于来源可信度。

这些问题必须交给 fetch、normalizer、source-quality 和 claim-grounding 层。

## 1.5：Typed client 是领域适配器

`structured_clients.py` 保留既有调用方使用的方法，例如 `extract_risks_chunked()`、
`decompose_requirements()` 和 `extract_supplier_relations()`。内部全部使用 typed Agents，外部返回
已有领域类型。

这样可以在不重写确定性 workflow 的情况下完成模型边界迁移。它不是第二套 runtime，也不是
generic JSON fallback。

## 1.6：仍需诚实说明的兼容行为

`src/agents/extraction_agent.py::_call_llm()` 捕获 typed client 异常后，会返回空
`ExtractionResult` 并附 warning；部分 filing/browser 路径也保留明确的业务 fallback。

因此当前系统已经消除手工 JSON 解析，但尚未把所有失败统一成一个 typed batch-failure model。
空结果只有连同 warnings、fallback events 或 `needs_review` 才能正确解释。

## 1.7：练习与验收

```bash
uv run python -m pytest -q \
  tests/ai/test_research_agent.py \
  tests/ai/test_structured_agents.py \
  tests/ai/test_structured_clients.py \
  tests/agents/test_extraction_agent.py
```

推荐练习：选择 `FilingRiskExtractionOutput` 或 `SupplierRelationBatch`，从测试反推字段约束、
validator、Agent builder、typed client 和 workflow consumer，画出完整类型流。

- [ ] Agent output 不使用 `dict[str, Any]` 代替领域 schema。
- [ ] `extra="forbid"` 能捕获意外字段。
- [ ] 空输出与 provider failure 不被自动解释成“没有风险”。
- [ ] 模型 confidence 与确定性 source trust 没有混为一谈。
- [ ] 评分、证据确认和报告仍由领域层负责。

下一章说明 run identity、权限、服务和预算如何通过 typed dependencies 进入这些 Agents。
