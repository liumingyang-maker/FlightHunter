# 72h 连续运行启动说明

## 前置

- Worker 已在跑：`data/daily_usage/worker.lock`（**不要杀**）
- 观测起点 `data/daily_usage/OBSERVATION.json` `started_utc` **只记不重置**

## 启动监控（新窗口，可关机后继续，采样追加 JSONL）

```powershell
cd C:\Users\97020\XiaomiMiMoProjects\FlightHunter
$env:PYTHONPATH='.'
# 后台 72h，每 15 分钟采样一次
.\.venv\Scripts\python.exe -B scripts\run_72h_monitor.py --interval 900 --duration 259200 --log data/daily_usage/logs/72h_samples.jsonl
```

## 中途生成报告

```powershell
.\.venv\Scripts\python.exe -B scripts\report_72h.py --log data/daily_usage/logs/72h_samples.jsonl --out docs/72H_RUN_REPORT.md
```

## 人工补充（脚本无法代替）

1. **断网/恢复**：拔网线或关 Wi-Fi ≥5 分钟再恢复，记时间点到 `docs/72H_RUN_REPORT.md`
2. **真实 toast**：触发通知 → 重启进程 → 确认不重复
3. **FlyNext 抽检 3 次**（不同时段）：记录条数/价格

## 诚实规则

- 采样时长 < 72h **不得**写「72h 达标」
- Worker 意外退出要如实记
- 不重置 OBSERVATION
