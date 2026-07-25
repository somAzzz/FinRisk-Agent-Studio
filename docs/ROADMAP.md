# FinRisk Agent Studio 路线图

最后更新：2026-07-25

路线图使用小版本 `v0.x`。当前目标是 `v0.1`；包和 Git tag 使用完整语义版本，例如 `0.1.0` 和 `v0.1.0`。

## 路线原则

1. 先保证 evidence、as-of、lineage、质量门禁和人工复核，再扩展 Agent 自治程度。
2. 每个版本必须同时交付代码、测试、降级语义、使用文档和至少一条可演示路径。
3. 外部 provider 不可用时必须明确降级，不得用 fixture 冒充实时结果。
4. 不新增直接投资建议、自动交易、LLM-only confirmed graph edge。

## v0.1：可发布的个人研究工作台

状态：**候选集成中**

目标：把已经完成的研究能力形成一个位于 `main`、可重复安装、可测试、可演示的首个小版本。

已完成：

- FinRisk 风险工作流、质量门禁与结构化报告。
- 供应链发现、图推理与 Sankey。
- Research Snapshot、变化检测、Thesis、Watchlist、Expectation、Alert 与复盘。
- 财务事实、行业模板、Peer Analysis、Scenario/Multiple/DCF 估值。
- Agent run、tool trace、候选证据和人工复核。
- Today、Company、Research Runs、Journal 多页面工作台。
- 数据库迁移、备份恢复、CI 和静态 demo。

剩余退出条件：

1. 产品重设计分支合入 `main`。
2. 合并候选通过全部发布门禁。
3. 更新验证记录与已知限制。
4. 确认并创建 `v0.1.0` tag。

不阻塞 v0.1：

- inline XBRL 分部维度；
- 外部 consensus 和自动 FX；
- 邮件/移动通知；
- 全仓 Ruff 归零；
- 长周期 Agent memory 校准。

## v0.2：Agent 可靠性与工程治理

目标：让 Agent 从“可审计地运行一次”提升为“可恢复地连续运行”。

工作包：

- Context Pack 的相关性、时效性、冲突和 token budget 评估。
- Evidence/graph/episodic memory 的失效、撤回和反馈闭环。
- Agent run checkpoint、跨进程恢复、幂等重试和取消。
- 长时间 Watchlist 扫描的状态、错误预算和运行摘要。
- 全仓 Ruff 分批清理，并逐步扩大 CI gate。
- 真实 Neo4j、SEC、transcript、search 和本地/远端 LLM 集成矩阵。

退出条件：

- 中断后的 Agent run 可以安全恢复且不重复写入。
- 记忆写入、召回、过期和撤回都有确定性测试。
- 关键真实 provider 有可重复的集成验收和明确跳过理由。
- Ruff 告警显著收敛，核心目录全量阻塞。

## v0.3：数据深度与比较质量

目标：提升财务、分部、预期和同行比较的真实性与可比性。

工作包：

- inline XBRL 或独立 provider 的 segment revenue/profit/geography。
- provider-neutral consensus contract 与修订历史。
- 有来源和 as-of 的自动 FX。
- 更多银行、SaaS、半导体、能源和生物科技 KPI。
- 财年错位、跨币种和 restatement 的更多真实负面案例。
- 同行历史分位与公司相对自身历史视图。

退出条件：

- 分部事实保持 raw label、来源和映射置信度，不自动伪标准化。
- consensus 与用户预期并列保存，不覆盖历史。
- 跨币种比较可以追溯到汇率来源和时间点。

## v0.4：持续监控与判断校准

目标：把本地研究闭环升级为长期运行、可解释的个人研究系统。

工作包：

- 邮件、webhook 或移动通知 adapter。
- filing、transcript、政策和供应链事件的独立 cursor。
- 多来源事件去重与可配置 materiality。
- guidance 命中率、来源冲突/撤回和 Thesis 结果校准。
- 长期运行健康检查、备份策略和恢复演练。

退出条件：

- 重复扫描不会重复提醒，provider 故障不丢失其他公司结果。
- 样本不足时只展示计数，不生成伪精确评分。
- 外部通知不保存明文凭证，并支持失败重试和审计。

## 优先级总表

| 优先级 | 工作 | 目标版本 |
| --- | --- | --- |
| P0 | 合并产品分支、重跑发布门禁、创建首个 tag | v0.1 |
| P1 | Agent memory、恢复、幂等与长期运行 | v0.2 |
| P1 | Ruff 治理与真实集成矩阵 | v0.2 |
| P1 | 分部、consensus、FX 和行业 KPI | v0.3 |
| P2 | 外部通知与长期判断校准 | v0.4 |

完成状态以 [STATUS.md](STATUS.md) 为准；路线范围改变时必须同步更新两份文档。
