# 个人研究闭环使用指南

本指南覆盖研究快照、跨期变化、市场预期、Watchlist 扫描、提醒和财报后复盘。所有输出用于研究记录，不构成投资建议。

## 1. 启动

```bash
uv sync
AUTH_DISABLED=1 uv run uvicorn src.api.main:app --reload
```

另一个终端启动前端：

```bash
cd frontend
npm install
npm run dev
```

生产或共享环境不要设置 `AUTH_DISABLED=1`；应配置 API key 并通过反向代理提供 TLS。

## 2. 数据文件

默认使用两个 SQLite 文件：

- `.cache/research_snapshots.sqlite`：快照、运行记录、变化、预期、提醒和复盘草稿。
- `.cache/research_journal.sqlite`：Thesis、Watchlist 和人工复盘。

可通过环境变量修改：

```bash
export RESEARCH_SNAPSHOT_PATH=/path/to/research.sqlite
export RESEARCH_JOURNAL_PATH=/path/to/journal.sqlite
```

## 3. 创建研究快照

前端进入 Research Journal → Research cycle，填写 ticker、财年和季度后选择 “Create snapshot”。

API 示例：

```bash
curl -X POST http://127.0.0.1:8000/research/runs \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","year":2026,"quarter":2,"include_management":true,"include_risks":true}'
```

返回的 `components` 会明确标记 `complete`、`partial`、`unavailable` 或 `failed`。某个 provider 不可用时，系统保留 partial snapshot，不会用 fixture 冒充真实数据。

如需在 FinRisk workflow 完成后自动固化包含风险报告的快照，可显式启用：

```bash
export RESEARCH_SNAPSHOT_ON_WORKFLOW=1
```

默认关闭该行为，避免现有 workflow 在用户不知情时增加 SEC 请求和数据库写入。也可以在 `POST /research/runs` 中传入 `workflow_run_id`，把指定 workflow 的结构化风险和证据带入快照。

## 4. 跨期变化

公司至少有两个快照后，前端会显示财务、风险、guidance、管理层和证据覆盖变化。每项变化包含 before/after、证据 ID、检测方式和 materiality。

用户可以选择：

- Confirm：确认变化有效。
- Review：标记需要进一步复核。
- Ignore：忽略该变化，并避免它继续进入研究队列。

## 5. 市场预期

可以在前端手工录入，或使用 CSV：

```csv
ticker,metric,fiscal_period,value,unit,source,observed_at,as_of,notes
AAPL,revenue,2026Q2,95000000000,USD,personal model,2026-06-30T00:00:00Z,2026-06-30T00:00:00Z,base case
```

预期按时间保存，不覆盖历史记录。财报提交之后形成的预期不能用于计算该期 surprise。

## 6. Watchlist 扫描

前端选择 “Scan watchlist”，或运行一次性 CLI：

```bash
uv run python main.py monitor --minimum-materiality medium --max-workers 2
```

常用选项：

```bash
# 只扫描指定公司
uv run python main.py monitor --ticker AAPL --ticker NVDA

# 查看结果但不写入快照、变化或提醒
uv run python main.py monitor --ticker AAPL --dry-run

# 固定知识截止日
uv run python main.py monitor --ticker AAPL --as-of 2026-06-30
```

个人部署建议使用 cron、launchd 或 systemd timer 调用该命令。CLI 对单公司失败进行隔离；只要任一公司失败，进程返回非零退出码。

## 7. 提醒与财报后复盘

来源指纹未变化时，重复扫描不会生成新快照或提醒。提醒确认或忽略后，同一 change ID 不会重复出现。

财报后复盘步骤：

1. 选择有两个快照且已关联 active Thesis 的公司。
2. 生成 Post-earnings review draft。
3. 检查锁定的原 Thesis、证伪条件、原假设、预期偏差和变化证据。
4. 人工确认 `supported`、`mixed` 或 `invalidated` 并填写结论。

系统的 suggested outcome 只是一条需要确认的研究提示，不会自动修改 Thesis。

## 8. 多公司比较与研究队列

比较要求各公司快照使用相同 `as_of` 和期间口径。币种不同的货币指标显示 `not_comparable`，不会直接混排。研究队列按需要复核的变化排序，不是投资评分或交易信号。

## 9. 备份与恢复

首次使用或升级代码后，先对 Snapshot 和 Journal 数据库执行幂等迁移：

```bash
SNAPSHOT_DB="${RESEARCH_SNAPSHOT_PATH:-.cache/research_snapshots.sqlite}"
JOURNAL_DB="${RESEARCH_JOURNAL_PATH:-.cache/research_journal.sqlite}"
uv run python main.py database migrate --path "$SNAPSHOT_DB"
uv run python main.py database migrate --path "$JOURNAL_DB"
```

备份使用 SQLite 在线 backup API，不需要直接复制正在写入的数据库文件：

```bash
uv run python main.py database backup --path "$SNAPSHOT_DB" \
  --destination "${SNAPSHOT_DB}.backup"
uv run python main.py database backup --path "$JOURNAL_DB" \
  --destination "${JOURNAL_DB}.backup"
```

恢复会以备份完整替换目标数据库。先停止 API 和扫描进程，再执行：

```bash
uv run python main.py database restore --path "$SNAPSHOT_DB" \
  --backup "${SNAPSHOT_DB}.backup"
uv run python main.py database restore --path "$JOURNAL_DB" \
  --backup "${JOURNAL_DB}.backup"
```

命令在迁移前、备份后和恢复后执行完整性检查；失败迁移会整体回滚。恢复后再调用 `/research/watchlist` 和 `/research/snapshots?ticker=AAPL` 做只读核验。
