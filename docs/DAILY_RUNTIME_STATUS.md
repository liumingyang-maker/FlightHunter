# FlightHunter · 日常运行状态收尾

- **报告 HEAD：** `73b1269`  
- **关系：** `a405b55` ⊂ `88ed828` ⊂ `73b1269`（无回退）  
- **测试：** 209 passed  
- **push/main：** 未做  

---

## 1. 进程盘点（精确匹配，无模糊批量杀进程）

| 角色 | PID | 配置 | 数据库 |
|---|---|---|---|
| **Web** | 8765 监听（python `app.cli web`） | `data/daily_usage/config.yaml` | `data/daily_usage/fh_daily.db` |
| **Worker** | 锁 PID **27368**（`alive=true`） | 同上 | 同上 |
| 旧 live_tests monitor | 已按 `monitor.py + live_tests` **精确停止** | — | 非日常库 |
| 旧双 Web | 已按 `app.cli web` 精确停止后只启 1 个 | — | — |

**未**用模糊关键词杀掉所有 Python/Worker。

### Worker 锁
- 路径：`data/daily_usage/worker.lock`  
- 心跳：`heartbeat_at` / `rounds` / `last_run_at`  
- **双开验证：** 第二次 `worker --once` → **exit=2**（拒绝重复启动）  
- **Windows 探活修复：** 不再用 `os.kill(pid,0)`，改用 `OpenProcess`（避免误判/误杀）  
- **project_root 修复：** CLI 固定为仓库根，避免 cwd 导致锁/库路径漂移  

### 启动项
`Startup\FlightHunterWorker.bat` → **仅**  
`worker --execute --config …\daily_usage\config.yaml --interval-seconds 3600`  
与 Web **同一业务库**，避免双 Worker/双库。

---

## 2. 数据库一致性与备份

| 项 | 结果 |
|---|---|
| Web/Worker 配置 | 同 `daily_usage/config.yaml` |
| SQLite | `data/daily_usage/fh_daily.db` |
| 备份 | `backups/fh_daily_20261030_124916.db` 等 |
| 恢复演练 | 复制备份打开 → sources=19, signals 可读 → 删除演练文件 |
| 正式库 | 未覆盖；`data/` 在 gitignore |

---

## 3. 监控起始时间（未重置）

`data/daily_usage/OBSERVATION.json`：

| 字段 | 值 |
|---|---|
| **started_utc** | **2026-10-30T03:55:25.6148611Z**（保留原值，不造假连续运行） |
| interval | 1800s（后台 worker）/ 启动项 3600s |
| worker_lock | `data/daily_usage/worker.lock` |

**累计有效运行时长：** 本报告时点约 **~55 分钟墙钟**（自 started_utc）。  
**72 小时：未达到 → 状态 = 持续观察中。**  
休眠/断网/关机/进程退出会中断墙钟；需在开机登录联网时由 Worker/锁心跳自然累计。

---

## 4. ChildProcess.kill

| 判断 | 说明 |
|---|---|
| 来源 | 执行工具会话中断提示 |
| 是否曾误杀 Worker | 本次收尾后 **无** 因 kill 导致的 Worker 异常退出记录 |
| 缓解 | 单实例锁 + 崩溃后 PID 死锁接管 + 启动项自动拉起 |

---

## 5. 故障与恢复（隔离）

| 场景 | 结果 |
|---|---|
| 来源指向 `127.0.0.1:9`（SSRF 拒绝） | `last_result=failed`，失败计数增加 |
| 恢复真实 URL 重扫 | 成功路径重置失败计数（existing candidate 路径已修） |
| 未对用户正常网络做断网 | **未** 修改全局电源策略 |

---

## 6. 情报质量统计（`intel-quality`）

| 指标 | 值 |
|---|---:|
| 抽样信号 | 22 |
| 24h 新发现 | 22 |
| 过期标记 | 0 |
| 情报视图 | 13 |
| 明确城市匹配 explicit_city | 1 |
| 全国/多城待核实 | 9 |
| 出发地未知 | 3 |
| 合并重复组 | 0 |
| 链接抽样 | **8/8 OK**（HTTP 200 ≠ 优惠仍有效） |

---

## 7. 来源分口径（source-health 摘要）

- fare 源 9；历史成功 6  
- 本轮成功/失败/冷却按 `last_attempt_at` 窗口统计（详见 CLI）  
- Fly4Free / Google News：robots → `manual_only` + failed  

---

## 8. 错误与恢复记录

1. 锁路径曾落在会话目录 → **已修** project_root  
2. Windows 探活失败导致双 Worker → **已修** OpenProcess  
3. 启动项曾指向默认库 → **已改为** daily_usage  
4. intel-quality 时区比较崩溃 → **已修**  

---

## 9. 结论

日常运行已收尾为 **单 Web + 单 Worker + 同库 + 文件锁 + 启动项自动恢复**。  
监控起点未改写；**72 小时未完成，标记为持续观察中**。  
继续开发安全；无需为凑时长空等。

Git：`develop` @ `73b1269` · 未 push · 未合并 main。
