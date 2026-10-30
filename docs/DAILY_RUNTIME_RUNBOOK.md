# DAILY_RUNTIME_RUNBOOK

## 启动（不影响正式库）

```powershell
# Worker（日常正式，勿乱杀）
.\.venv\Scripts\python.exe -m app.cli worker --config data\daily_usage\config.yaml

# Web
.\.venv\Scripts\python.exe -m app.cli web --config data\daily_usage\config.yaml
```

## 迁移

- 新库：自动 `create_all_new_db` + Alembic head 校验  
- 已有库：**不**静默改表；启动日志提示 `needs_migration` / `outdated`  
- 正式升级（**需用户授权**）：
  1. 备份 `data\daily_usage\fh_daily.db`  
  2. `.\.venv\Scripts\python.exe -m alembic upgrade head`  
  3. 验证 `check_alembic_head` → `in_sync`  

## 隔离演练

```powershell
.\.venv\Scripts\python.exe -B scripts\isolated_migrate_drill.py
.\.venv\Scripts\python.exe -B scripts\smoke_after_codex_merge.py
```

## 观测起点

- `data/daily_usage/OBSERVATION.json` 的 `started_utc` **只记不重置**  
- Worker 单实例锁：`data/daily_usage/worker.lock`  
- 按 CommandLine 精确匹配杀进程，禁止批量杀 Python  

## 来源健康

- `ok` / `ok_existing` / `ok_zero` / `ok_valuable` / `failed`  
- `ok_existing` = 有解析无新增，**不是**零解析  

## 通知

见 `docs/NOTIFY_DELIVERY_SEMANTICS.md`（at-most-once + 失败≤3；非 exactly-once）
