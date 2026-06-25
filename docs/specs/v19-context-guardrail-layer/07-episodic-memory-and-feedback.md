# 07 - Episodic Memory 与 Feedback

## 目标

让系统记住过去 workflow 的成功和失败，避免重复犯错。

## WorkflowEpisode

字段：

- `run_id`
- `task_type`
- `input_fingerprint`
- `successful_queries`
- `failed_queries`
- `accepted_claims`
- `rejected_claims`
- `rejected_graph_edges`
- `guardrail_failures`
- `evaluation_status`
- `lessons`

## Negative Memory

示例：

```text
Previous run rejected "OpenAI directly buys GPUs from NVIDIA" because evidence only supported Azure infrastructure dependency.
```

用途：

- 进入 Supplier Discovery。
- 进入 Report Generator。
- 进入 Claim Grounding Validator。

## Feedback API

后续新增：

```text
POST /memory/feedback
```

支持：

- accept memory。
- reject memory。
- mark stale。
- attach correction。

## MVP

MVP 只实现模型和 store 写入，不接前端。
