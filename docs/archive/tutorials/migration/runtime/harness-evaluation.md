# Harness 决策实验

> 当前事实：FinRisk 没有安装或使用 `pydantic-ai-harness`。本文定义未来如何评估，
> 不表示应当引入它。

## 决策问题

只有当 Core Agent + Pydantic Graph 的具体缺口已被可重复 case 证明时，才开始试验。
试验不问“Harness 能不能运行”，而问：

- 它是否在不降低 grounding 和权限隔离的情况下提高任务成功率？
- 它是否减少可维护的自定义代码，而不是再造一层 wrapper？
- 计划、子任务、工具输出和 usage 是否能稳定投影到现有 trace/API？
- 请求、tool call、token、deadline 和 domain budget 是否仍有唯一所有者？

## 实验前提

1. 记录当前 `uv.lock` 中 Pydantic AI 版本。
2. 从官方发布说明选择与当前 Core 兼容的 Harness 版本。
3. 只在专用实验分支/依赖组中精确 pin，不预先修改生产依赖。
4. 冻结 Core baseline 的 case、配置、model revision 和评估器。
5. 在任何费用型 live 试验前先跑离线合同测试。

不在文档中固定一个已过时版本号。每次试验的确切版本应写入当次报告和 lockfile。

## Baseline 和指标

| 类别 | 建议指标 |
| --- | --- |
| 质量 | task success、unsupported claim、source coverage、verdict consistency |
| 安全 | 未授权工具暴露/执行、approval bypass、secret/PII trace leakage |
| 预算 | requests、tool calls、input/output tokens、domain operations、deadline |
| 稳定性 | validation retry、partial failure、resume/idempotency、provider error taxonomy |
| 可观测性 | message/tool/plan/delegation/usage/latency 的关联率 |
| 运维成本 | 新增代码、自定义 adapter、升级风险、回滚复杂度 |

必须用同一组 case 和评估器比较 Core baseline 与实验组。

## 逐项实验

每次只添加一项候选能力，例如 planning、subagents 或 tool-output limiting。每项按以下顺序：

1. 写出 Core baseline 的具体缺口；
2. 定义可机械判定的通过阈值和退出条件；
3. 对一个受限 workflow 做最小集成；
4. 跑离线 contract/security/budget tests；
5. 只对通过离线门的候选跑 live 比较；
6. 记录 accept/reject 和原始指标；
7. 拒绝的能力立即删除代码与依赖。

## 不可协商的门

- Harness planning 不能取代持久化业务 workflow state。
- Subagent 不能继承超出任务范围的工具或 tenant 权限。
- Tool-output limiting 不能破坏 evidence locator、hash 或重要失败信息。
- Memory 不能直接晋升为 evidence 或跳过审批。
- Harness approval 不能代替 server-side authentication/authorization 和 replay protection。
- 新能力不能引入第二套长期 runtime。

## 接受与收尾

只有一项能力同时满足以下条件才能合并：

- 对已证明的缺口有明显改善；
- unsupported claim 和安全指标不恶化；
- 预算和 trace 合同可机械验证；
- 没有更简单的 Core/Graph 修复能实现同样结果；
- 有 ADR、升级说明、运行手册和 rollback revision。

否则结论是 reject，而不是“暂时保留代码以后再看”。
