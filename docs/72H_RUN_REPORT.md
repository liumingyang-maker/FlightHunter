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


## 网络中断/恢复实验（2026-10-31T02:49Z）

| 阶段 | 结果 | 说明 |
|---|---|---|
| before | 源计数 20 / success 7 / failed 9 | 基线 |
| **blocked** | `fetch_ok=false`，`error=URL_NOT_PUBLIC` | socket 故障注入；DNS 失败 **fail-closed**（安全行为） |
| **recovered** | `fetch_ok=true`，HTTP **200** | FlyNext 真实恢复 |

- **方式：** 应用层 socket `getaddrinfo` 注入（远程无法物理断网；防火墙需管理员）
- **非**物理拔网；向日葵保持连接
- **代码：** `scripts/net_fault_inject_test.py`（可重复）
- **日志：** `data/daily_usage/logs/net_sim_test.jsonl`
