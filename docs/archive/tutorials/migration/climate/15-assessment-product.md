# Chapter 15：确定性 Assessment、报告与产品接入

> 路线状态：条件式迁移实验，尚未在 FinRisk 实施。API、存储与前端路径
> 都是待批准工作包，不应出现在当前能力或发布承诺中。

## 本章结果

本章将已验证证据按 registry rubric 聚合成五状态 requirement assessment，生成可审计报告，并接入
FinRisk run store、API、人工审核和前端。完成后用户可以查看“找到什么、缺什么、哪里失败”，但
系统不发布伪精确的企业总分或自动合规结论。

前置条件：Chapter 14 的 evidence、mapping、verification 和 metric artifacts 已通过 gate。

## 设计决定

1. 最终状态由纯函数/规则聚合器决定，不由 summary Agent 决定。
2. completeness 优先于 `not_found`；关键阶段不完整时使用 `uncertain`。
3. 披露状态与气候财务风险评分分开。
4. 报告数字从 `DisclosureProfile` 渲染，不由 LLM 重算。
5. 人工审核是有审计的状态转换，审核后重新运行确定性聚合。
6. 新入口先受 feature flag 控制，不改变现有 FinRisk workflow 默认行为。

## 文件变更总览

### 新建后端

```text
src/domains/climate/assessment.py
src/reports/climate.py
src/workflows/climate_disclosure.py
src/api/climate_disclosures.py
src/api/climate_store.py                 # 或扩展通用 run-store protocol
tests/domains/climate/test_assessment.py
tests/reports/test_climate_report.py
tests/workflows/test_climate_disclosure.py
tests/api/test_climate_disclosures.py
```

### 新建前端

```text
frontend/src/features/climate-disclosure/
  ClimateDisclosurePage.tsx
  RequirementMatrix.tsx
  EvidenceInspector.tsx
  MetricTable.tsx
  ReviewQueue.tsx
  types.ts
  *.test.tsx
```

### 修改

- `src/api/main.py`：注册受相同 auth/rate-limit 保护的 router；
- `src/agents/state.py`：只扩展通用 `HumanReviewObjectType`，不塞入整个 climate state；
- `frontend/src/App.tsx` 和路由/导航：增加 Climate 入口；
- API client/types：增加版本化 climate wire contract；
- `src/config.py`、`.env.example`：增加默认关闭的 feature flag 和安全限制。

## 15.1：固定聚合顺序

对每个 requirement 按以下顺序执行：

```text
1. applicability
2. input/stage completeness
3. verified present rubric
4. verified partial rubric
5. complete search with no minimum evidence -> not_found
```

具体语义：

- 确定性适用性规则满足排除条件 → `not_applicable`；
- ingestion/retrieval/extraction/verification 关键阶段不完整或冲突未决 → `uncertain`；
- verified evidence 满足完整 rubric → `present`；
- 只满足部分必要元素 → `partial`；
- 分析完整且没有最低支持证据 → `not_found`。

顺序不可交换。尤其不能先因为 candidate 为空填 `not_found`，再忽略 retrieval channel failure。

## 15.2：rubric rule engine

`assessment.py` 输入 registry、verified mappings、metrics、issues 和 completeness summary，输出
`RequirementAssessment`。要求：

- 每条命中 rule 记录 `rubric_rule_id`；
- supporting 与 contradictory evidence 分开；
- 相同 evidence 去重但不丢 mapping provenance；
- requirement-specific 必要元素来自 registry，不散落在 `if requirement_id == ...`；
- 同样输入得到相同状态和排序；
- 所有计数可由 assessments 独立重算。

模型 rationale 可以显示为辅助说明，但不参与分支条件。

## 15.3：profile 指标

至少输出：

- 五状态 counts；
- applicable count；
- completed count；
- analysis completion；
- completed-item coverage；
- conservative coverage；
- failure、uncertain、not_found 和 review-pending 数。

每个公式在 domain docstring 和报告说明中固定。MVP 不输出：

- 单一企业总分；
- 合规/认证徽章；
- 跨公司排名；
- “未找到 = 企业未披露”的绝对措辞。

## 15.4：确定性报告

`src/reports/climate.py` 从 profile 渲染 typed payload 和 Markdown/HTML projection，至少包含：

1. issuer、报告、期间、输入质量；
2. framework/profile/edition/registry version；
3. requirement matrix；
4. verified quote、locator、mapping/verdict；
5. metric raw/normalized 值与 issues；
6. contradictory evidence 和 review 状态；
7. completeness、failures、limitations；
8. 明确的非合规审计免责声明。

summary Agent 如后续加入，只能读取 profile 并返回引用 assessment/evidence ID 的叙述；统计数字仍由
renderer 注入。

## 15.5：workflow 与 checkpoint

`climate_disclosure.py` 编排：

```text
ingest
  -> load profile
  -> retrieve by requirement
  -> extract evidence
  -> deterministic locator validation
  -> verify mappings
  -> parse metrics
  -> deterministic assessment
  -> report
  -> quality gate / human review
```

每阶段写版本化 checkpoint。resume 读取 manifest，只运行未完成 item；输入、registry、prompt/model
或 schema major 改变时不能复用不兼容缓存。

## 15.6：API

建议独立前缀：

```text
POST /climate-disclosures/runs
GET  /climate-disclosures/runs/{run_id}
GET  /climate-disclosures/runs/{run_id}/profile
GET  /climate-disclosures/runs/{run_id}/evidence
GET  /climate-disclosures/runs/{run_id}/trace
GET  /climate-disclosures/runs/{run_id}/artifacts
POST /climate-disclosures/runs/{run_id}/reviews/{item_id}
```

request 不接受客户端自报“允许外传原文”“跳过验证”等安全 flag。服务端根据 principal、配置和数据
inventory 决定 policy。未知 run、跨 tenant、重复 review 和过期状态都有明确响应。

## 15.7：人工审核

扩展 `HumanReviewObjectType` 支持：

```text
climate_evidence
requirement_mapping
metric_observation
assessment_conflict
```

review 记录 reviewer、时间、reason、旧值、新值和关联 artifact hash。批准 evidence 不能跳过 locator
校验；修改 mapping/metric 后标记下游 assessment/report stale，并重新确定性计算。

## 15.8：前端

复用现有 shell、timeline、review action 和 evidence card 交互模式，但新建领域视图：

- requirement matrix 按 framework/pillar 展示五状态；
- evidence inspector 并排显示原文、summary、locator 和 verifier；
- metric table 同时显示 raw、normalized、unit/period/scope issues；
- completeness/failure 与 coverage 同屏；
- review-pending 不被绿色完成状态掩盖；
- 不把 risk score card 改标题后当 disclosure score。

测试桌面、移动、键盘操作、颜色以外的状态表达和长中文/英文 quote。

## 15.9：feature flag 与回滚

feature flag 只控制新入口是否可用，不控制同一请求在两套 climate runtime 间切换。关闭 flag 后：

- 现有 `/workflows`、research 和 supply-chain 行为不变；
- 已写 climate artifacts 保留可读；
- 不删除或改写现有 FinRisk 数据；
- 回滚部署版本时 schema reader 有明确兼容范围。

## 本章验收

```bash
uv run pytest -q \
  tests/domains/climate/test_assessment.py \
  tests/reports/test_climate_report.py \
  tests/workflows/test_climate_disclosure.py \
  tests/api/test_climate_disclosures.py
uv run pytest -q tests/workflows tests/api tests/reports
uv run ruff check src/domains/climate src/reports src/workflows src/api
cd frontend && npm test && npm run build
```

- [ ] 五状态由确定性规则按固定顺序产生。
- [ ] `present/partial` 100% 引用 verified evidence。
- [ ] report 数字与 profile 完全一致。
- [ ] review 不能绕过 locator，且会触发下游重算。
- [ ] API 继承认证、授权、限流、脱敏和 tenant 隔离。
- [ ] feature flag 关闭时现有产品无回归。

本章建议提交：

```text
ch15: add deterministic climate assessment and product workflow
```
