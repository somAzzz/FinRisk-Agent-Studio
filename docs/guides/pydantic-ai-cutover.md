# Pydantic AI 切流与回滚 Runbook

本文将 [Pydantic AI 迁移方案](../PYDANTIC_AI_MIGRATION.md) 的 PAI-7 门禁转成
可重复执行的运维步骤。默认值在所有门禁通过前必须保持 `legacy`。

## 1. 前置条件

1. 使用 SQLite 持久化 run state：

   ```bash
   export RUN_STORE_BACKEND=sqlite
   export RUN_STORE_DB=.cache/finrisk_agent_studio/runs.sqlite3
   ```

2. 为目标 provider 配置 endpoint、model 和凭据。不得使用 `EMPTY`、`dummy`、
   `REPLACE_ME` 等公网 provider 占位凭据。
3. 备份 `RUN_STORE_DB`，记录当前 commit，并创建可部署的迁移前 tag。
4. 先运行全量非 integration 测试和 demo 门禁。

## 2. Live provider 合同

Live 工具只发送合成提示，调用一个返回整数 `7` 的本地只读工具，不读取或发送项目、
客户、研究或数据库内容。每个候选 provider 都应执行一次：

```bash
uv run python scripts/pydantic_ai_live_acceptance.py \
  --provider sglang \
  --output artifacts/pydantic-ai/sglang-live.json

uv run python scripts/pydantic_ai_live_acceptance.py \
  --provider vllm \
  --output artifacts/pydantic-ai/vllm-live.json

uv run python scripts/pydantic_ai_live_acceptance.py \
  --provider deepseek \
  --output artifacts/pydantic-ai/deepseek-live.json
```

需要覆盖默认配置时使用 `--base-url` 和 `--model`。退出码 `0` 表示同时满足：

- provider 请求成功；
- `local_probe` 恰好调用一次且参数为 `7`；
- 返回值通过 `LiveAcceptanceOutput` 严格验证；
- 报告包含 request 和 token usage。

退出码 `1` 表示失败。错误报告经过脱敏；不得为了得到绿色结果而关闭 schema、跳过
tool call 或改用客户端伪造结果。

## 3. Primary 观察期

Live 合同通过后，在部署配置中显式设置：

```bash
export AGENT_RUNTIME_MODE=pydantic_ai_primary
```

`/agent-runs` 会把实际 `runtime_mode` 持久化到每个 `AgentRunState`。旧记录缺少该
字段时按 `legacy` 读取，不会被误算为 primary 样本。

默认观察门禁要求至少 20 个 primary run、168 小时、无失败、无非终态 run，且
emergency fallback 使用量为零：

```bash
uv run python scripts/pydantic_ai_observation_gate.py \
  --db .cache/finrisk_agent_studio/runs.sqlite3 \
  --required-runs 20 \
  --required-hours 168 \
  --output artifacts/pydantic-ai/primary-observation.json
```

退出码 `0` 才表示观察门禁通过；退出码 `2` 表示报告中的 `blockers` 非空。
`needs_review` 是证据质量终态，不单独计为 runtime failure，但其中若包含 fallback
event，仍会阻止切流。

修改运行数或观察时长必须在发布审批记录中说明理由，不能只为绕过失败门禁而降低。

## 4. 默认切换检查表

只有下列项目全部有机器证据时，才修改 `src/config.py` 和 `.env.example` 的默认值：

1. 关键 live provider JSON 报告为 `pass`；
2. primary observation JSON 的 `ready=true`；
3. golden/eval 不低于 PAI-0 基线；
4. API、trace、review、resume、approval、demo、cached 合同通过；
5. 变更范围 Ruff、lockfile、import-all 和全量非 integration 测试通过；
6. `rg` 生成并人工确认 legacy 生产引用清单；
7. `ARCHITECTURE.md`、`STATUS.md` 和 PAI-7 验收记录更新；
8. 迁移前 tag 可以在目标环境部署。

默认切换后仍保留 `AGENT_RUNTIME_MODE=legacy` emergency override 至少一个发布周期，
并继续运行 observation gate。只有 fallback 为零且没有回滚事件，才进入 legacy 删除。

## 5. 回滚

观察期或默认切换后出现 provider、schema、tool、质量或延迟回归时：

1. 立即设置 `AGENT_RUNTIME_MODE=legacy` 并滚动重启应用；
2. 保留失败 run、message batch、trace 和 live/observation JSON，不删除证据；
3. 确认旧 SQLite run 仍可读取；
4. 在 PAI-7 验收记录中登记触发原因、影响 run 和恢复时间；
5. 修复后重新从 live 合同开始，不沿用失败前的观察窗口。

legacy 代码删除后不再使用 feature flag 回滚，而是部署迁移前 tag。因此删除前必须
再次验证 tag、数据库副本恢复和发布产物。
