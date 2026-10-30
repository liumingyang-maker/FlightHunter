# FlightHunter 需求完成矩阵（诚实口径 · 2026-10-31 冲刺收尾）

**HEAD：** 冲刺收尾批（P0–P5）  
**基线文档：** `docs/PRODUCT_BASELINE_20261030.md` + `docs/SPRINT_CLOSEOUT_PLAN.md`  
**口径：** `done` = 可调用实现 + 证据；`partial` = 有代码未闭环；`blocked` = 外部授权；`not_implemented` = 无实现。  
**测试数量 ≠ 104 项验收。**

## 汇总（诚实）

| 状态 | 说明 |
|---|---|
| done | P0 安全层、P1 样本语义、P2 三态、P3 状态机、P4 迁移检查 |
| partial | 浏览器 IP 绑定、跨源合并、旅行日期抽取、通知 exactly-once |
| NOT_TESTED | 104 项全量、72h、真实 toast、公网 |
| blocked | 实时报价 API（V1 非必需）、IMAP、未授权供应商 |

## P0 安全（本轮）

| ID | 状态 | 证据 |
|---|---|---|
| SEC-S1 连接期公网 IP 绑定 | done | `PublicAddressBackend` + 测试 |
| SEC-S2 浏览器目标/子资源拦截 | done | `browser_safety.py` + 8 测试 |
| SEC-S3 shared 100.64/10 拒绝 | done | `is_global` |
| SEC-S4 httpcore 依赖锁定 | done | pyproject `httpcore>=1,<2` |

## P1 情报语义

| ID | 状态 | 证据 |
|---|---|---|
| FAR-P1-01 出发地多选/全国/HKG-MFM | done | `airports/china.py` |
| FAR-P1-02 国际过滤（含跨境 HKG↔PVG） | done | `is_international_pair` |
| FAR-P1-05 多价不串 | done | 样本 20/20 `scripts/label_samples.py` |
| FAR-P1-07 反馈筛选 | done | user_feedback ↔ signal_status |
| FAR-P1-08 发布/旅行/发现分列 | done | `_extract_published_only` + travel 窗口 |
| FAR-LIVE-01 真实抓取 | partial | FlyNext 只读 200；其它源受限 |

## P2 抽奖

| ID | 状态 | 证据 |
|---|---|---|
| GIV-CN-02 核心推荐三态 | done | `core_recommend.py` + 6 测试 |
| GIV-CN-03 页面分栏 | done | campaigns.html verify/类型/出境/核心 |
| GIV-资格三态 | done | 缺档案 unknown |

## P3 行程/通知

| ID | 状态 | 证据 |
|---|---|---|
| TRP-CONFIRM-01 确认才扫 | done | 6 测矩阵 |
| TRP-N-007/R-016 开关组合 | done | fare_monitor 尊重设置 |
| NTF-送达语义 | partial | at-most-once + ≤3；非 exactly-once |

## P4 数据库

| ID | 状态 | 证据 |
|---|---|---|
| DB-迁移检查 | done | in_sync/outdated/no_version |
| DB-旧库不改表 | done | Web/CLI `prepare_engine` |
| DB-隔离演练 | done | `isolated_migrate_drill.py` |

## P5 验收

| ID | 状态 | 证据 |
|---|---|---|
| 单元测试 | done | **304 passed** |
| 标注样本 | done | 20/20 |
| R 系列自查 | done | 18/18 |
| 104 项全量 | **NOT_TESTED** | 待 Codex/人工 |
| 72h 连续 | **NOT_TESTED** | 观测不重置 |
| 真实桌面 toast | **NOT_TESTED** | 见 NOTIFY 文档 |

## 需求调整记录（非假装已开发）

| 旧强制项 | 新状态 |
|---|---|
| 实时机票报价供应商 | **V1.0 取消** — 情报+来源链接为完整能力 |
| 自动购票/报名 | **永不做** |

**不得声称 114/104 全部 done。**
