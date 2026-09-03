# Pydantic AI PAI-0 基线记录

- 采集日期：2026-08-23
- 默认运行时：`legacy`
- 状态：通过

## 全量非集成测试

```text
python -m pytest -m 'not integration' -q --maxfail=1
970 passed, 1 skipped, 8 deselected in 16.73s
```

沙箱内首次执行时，一个公共域名解析测试因网络隔离失败；在获批的正常网络
环境中以同一命令复跑后通过。上述结果是验收采用的权威基线。

## 固化的迁移契约

- 基线清单：`tests/fixtures/pydantic_ai_migration/baseline_manifest.json`；
- 13 个工具的 name/schema/scope/risk/evidence kind：
  `tests/fixtures/pydantic_ai_migration/tool_catalog_baseline.json`；
- 代表案例：FinRisk、Supply Chain、generic research；
- 既有 graph/report payload contract fixtures；
- `AGENT_RUNTIME_MODE=legacy` 仍是默认值。

工具快照由 `tests/tools/test_tool_catalog_baseline.py` 在测试时重新计算，任何
工具 schema 或治理 metadata 变化都必须经过显式评审并更新基线。
