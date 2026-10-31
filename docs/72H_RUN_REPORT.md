# 72 小时连续运行报告（自动汇总）

- **样本数：** 2
- **采样窗口：** `2026-10-31T02:39:00+00:00` → `2026-10-31T02:39:02+00:00`（约 0.0 小时）
- **观测起点（只读）：** `2026-10-30T03:55:25.6148611Z`
- **Worker PID 集合：** 
- **心跳变化次数：** 0
- **采样错误：** 0

## Worker

| 项 | 首次 | 末次 |
|---|---|---|
| rounds | None | None |
| last_run_at | None | None |
| heartbeat_at | None | None |

## 来源健康（末次 24h 窗口）

```json
{
  "sources_total": 20,
  "historically_fetched": 12,
  "round_success": 7,
  "round_failed": 9,
  "round_zero_parse": 6,
  "round_existing": 0,
  "round_valuable": 1,
  "round_cooldown": 4,
  "round_not_attempted": 0
}
```

## 诚实边界

- 本报告由 **采样 JSONL** 汇总，不代表 104 项验收。
- 未覆盖：真实桌面 toast、断网/恢复实验（需人工操作）、公网。
- 若 `duration` < 72h，**不得**声称 72h 达标。

## 原始样本

`data\daily_usage\logs\72h_smoke.jsonl`
