# Codex / GPT 独立复验任务书（冲刺收尾批）

**日期：** 2026-10-31  
**基线：** `develop` 冲刺收尾批（在 `9c6d83c` 合并 Codex `bca4a4f` 之后继续 P0–P5）  
**目的：** 独立复验，**不要**只看 iMiMo 自测；判定「个人日常可靠使用」与「完整 V1.0」是否可关单。

---

## 1. 请你核对的改动主题

| 主题 | 位置 |
|---|---|
| 浏览器目标/子资源公网拦截 | `app/core/browser_safety.py` |
| 标注样本集 20 条 | `scripts/label_samples.py` |
| 多价 UI / multi_price | `app/services/fare/intel.py` · `fare.html` |
| core_recommend 正向三态 | `app/services/raffle/core_recommend.py` |
| 行程开关矩阵 | `tests/unit/test_p3_trip_matrix.py` |
| 通知语义文档 | `docs/NOTIFY_DELIVERY_SEMANTICS.md` |
| CLI 旧库不改表 | `app/db/session.py::prepare_engine` · `app/cli.py` |
| 运行手册 | `docs/DAILY_RUNTIME_RUNBOOK.md` |
| 需求矩阵 | `docs/REQUIREMENTS_MATRIX.md` |

## 2. 建议独立操作（勿改正式库）

```powershell
# 1) 全量单测
$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe -B -m pytest tests/unit -q -p no:cacheprovider

# 2) 标注样本
.\.venv\Scripts\python.exe -B scripts\label_samples.py

# 3) R 系列安全自查
.\.venv\Scripts\python.exe -B scripts\selfcheck_r_series.py

# 4) 合并后隔离冒烟
.\.venv\Scripts\python.exe -B scripts\smoke_after_codex_merge.py

# 5) 迁移演练
.\.venv\Scripts\python.exe -B scripts\isolated_migrate_drill.py
```

## 3. 请重点打穿的边界（负例优先）

1. 价格：`香港出发 台湾 HK$800 · 大阪 HK$1500` 是否仍可能串到视图层（不只 parse）  
2. `Cathay flight SIN to JFK` / `国泰航空纽约飞伦敦` 是否误判 HKG  
3. robots 403 / 公开→私网重定向 / 无 Content-Length 超大流  
4. 确认行程 + `auto_attach_fare_watch_to_new_trip=false`  
5. `core_recommend`：国内航班 / 不包括大陆 / candidate 三种负例  
6. 旧库启动后表清单是否被 `create_all` 改写  
7. toast 成功后清空进程状态是否重复外送  

## 4. 请给结论的三问

| 问题 | YES / NO | 依据 |
|---|---|---|
| 安全可靠的个人日常使用？ |  |  |
| 满足完整 V1.0？ |  |  |
| 可公开上线（技术安全）？ |  |  |

## 5. 明确未做 / 不要求本轮完成

- 104 项逐条全量  
- 72 小时连续运行独立证据  
- 真实桌面 toast 实机  
- 公网渗透 / CSP / 多租户  
- 实时报价 API  
- 自动购票/报名  

## 6. 交付物清单

- `docs/SPRINT_CLOSEOUT_PLAN.md`（计划）  
- `docs/REQUIREMENTS_MATRIX.md`（诚实矩阵）  
- `docs/NOTIFY_DELIVERY_SEMANTICS.md` / `docs/DAILY_RUNTIME_RUNBOOK.md` / `docs/TECH_DEBT.md`  
- 代码与测试（见 git log）  
- 建议快照：`git archive HEAD`  

**iMiMo 不自签关单；以你的独立复验为准。**
