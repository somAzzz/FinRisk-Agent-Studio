# 04 - FinRisk Primary Agent Workflow

## 目标

把 FinRisk 从“固定 workflow + 局部 LLM tool loop”迁移到 agent-level primary workflow。LLM planner 负责决定 filing、market、transcript、financial metrics、graph 的查询顺序；workflow 负责验证、写 state、打分和报告。

## 当前基线

已有：

- `FinRiskWorkflowState`
- `MarketExplorerStep(llm_mode="primary")`
- filing extractor LLM fallback + keyword fallback
- evidence normalizer、risk scorer、graph reasoner、report generator
- quality-gated orchestrator

缺口：

- planner 不能跨 step 决策。
- filing / transcript / financial / graph 查询还不是 agent subgoals。
- report generator 还未消费 unified evidence candidate manifest。
- human review 未形成 agent-level decision。

## Agent Flow

FinRisk primary path：

```text
user goal
  -> AgentRunState(workflow_kind="finrisk")
  -> planner creates subgoals:
       identify filing risks
       collect market evidence
       check transcript commentary
       check financial metrics / XBRL
       query graph paths
       decide report readiness
  -> each subgoal calls LLMToolAgentRuntime with scoped tools
  -> EvidenceCandidateNormalizer
  -> FinRiskEvidenceAdapter
  -> existing workflow state
  -> quality gates
  -> report
```

## Tool Scopes

FinRisk agent may use:

- `company_research`
- `finrisk_market`
- future `finrisk_filing`

Allowed tools:

- `sec_list_filings`
- `sec_fetch_filing`
- `web_search`
- `web_fetch`
- `search_and_fetch`
- `transcript_lookup`
- `financial_metrics_lookup`
- `xbrl_fact_lookup`
- `graph_query`
- `graph_path_search`
- `browser_explore`

Not allowed:

- graph write。
- report write。
- memory write。
- raw Cypher。
- low-level browser `click/type/scroll`。

## State Writes

Agent 不能直接写：

- `filing_risks`
- `market_evidence`
- `normalized_evidence`
- `risk_scores`
- `report`

写入路径必须是：

```text
EvidenceCandidate
  -> FinRiskEvidenceAdapter
  -> existing workflow step / validator
  -> FinRiskWorkflowState
```

## Report Readiness

Agent 只有在以下条件满足时可进入 report generation：

- 至少一个 filing evidence accepted。
- 每个 top risk 至少一个相关 evidence。
- market evidence 如果低质量，必须标 uncertainty。
- graph insight 必须绑定 graph path evidence。
- source quality validator 没有 fail-level finding。

否则 planner 必须：

- 继续查证；
- fallback deterministic/cached；
- 或创建 human review item。

## Migration Steps

### Step 1 - Agent Wrapper

新增 `FinRiskAgentWorkflowRunner`，包装现有 `run_finrisk_workflow`。

第一版只生成 `AgentRunState` 和 subgoals，不改变最终输出。

### Step 2 - Evidence Candidate Ingestion

把 `MarketExplorerStep` 的 tool event parsing 替换为 unified normalizer。

### Step 3 - Filing / Transcript / Metrics Subgoals

Planner 可创建 filing、transcript、financial metrics subgoals。工具结果进入 candidates，adapter 决定是否进入 state。

### Step 4 - Agent Primary Report Path

当 evidence readiness 满足时，运行现有 scoring/report generator。

### Step 5 - Review / Fallback

证据不足或冲突时，状态变成 `needs_review`，并保留 deterministic fallback 输出。

## 测试

新增：

```text
tests/workflows/test_finrisk_agent_workflow.py
tests/agents/test_finrisk_agent_readiness.py
```

覆盖：

- agent wrapper 不破坏 demo mode。
- planner 生成 filing/market/graph subgoals。
- accepted candidates 进入 `FinRiskWorkflowState`。
- low-quality candidates 不进入 report。
- report readiness 不足触发 `needs_review`。
- deterministic fallback 仍可用。

## 验收

```bash
uv run pytest tests/workflows/test_finrisk_agent_workflow.py tests/agents/test_finrisk_agent_readiness.py -q
uv run pytest tests/workflows tests/evaluation -q
```
