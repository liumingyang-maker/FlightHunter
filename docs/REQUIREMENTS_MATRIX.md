# FlightHunter 需求完成矩阵（诚实口径 · 2026-10-30 产品方向调整后）

**HEAD：** `aecb6dc` 起在 `develop` 演进  
**基线文档：** `docs/PRODUCT_BASELINE_20261030.md`  
**口径：** `done` = 可调用实现 + 证据；`partial` = 有代码未闭环；`blocked` = 外部授权；`not_implemented` = 无实现。**测试数量 ≠ 104 项验收。**

## 需求调整记录（非假装已开发）

| 旧强制项 | 新状态 |
|---|---|
| 实时机票报价供应商 / urgent_verified 可购价 | **需求取消（V1.0）** — 适配器代码保留，情报+来源链接为完整能力 |
| 无报价导致雷达不可用 | **否** — P1 情报模式 |

## 汇总

| 状态 | 约计 |
|---|---|
| done | 核心 P1/P2/P3 子能力 + 既有安全/调度/OCR |
| partial | 跨源去重、部分源 robots、UI 多选控件 |
| blocked | IMAP、部分国际源、未授权供应商 |

## P1 机票情报（新优先级最高）

| ID | 状态 | 证据 |
|---|---|---|
| FAR-P1-01 出发地多选/全国/HKG-MFM | done（服务层+API） | `airports/china.py` · 256 内地机场 · 测试 |
| FAR-P1-02 国际航线过滤 | done | `is_international_pair` 排除纯内地 |
| FAR-P1-03 情报分类 | done | intel.py classify |
| FAR-P1-04 无报价可用 | done | `/api/v1/fare/intel` |
| FAR-P1-05 去重 | partial | deal dedup_key |
| FAR-P1-06 过期过滤 | done | hide_expired |
| FAR-P1-07 用户反馈 | done（状态字段） | bookmarked/read/not_interested… |
| FAR-LIVE-01 真实抓取 | partial | smzdm 成功；secretflying robots 失败 |

## P2 抽奖

| ID | 状态 | 证据 |
|---|---|---|
| GIV-CN-01 出境标签 | done | tags.china_outbound_relevance |
| GIV-CN-02 核心推荐过滤 | done | core_recommend + not_travel_ticket |
| GIV-原有 | 保留 partial/done 子集 | LOCAL AIRPORT 回归 |

## P3 行程福利

| ID | 状态 | 证据 |
|---|---|---|
| TRP-CONFIRM-01 确认才扫描 | done | trips.confirmed + create/confirm/cancel |
| TRP-原有 | partial | 指南/卡包等 |

## 安全门槛

不自动外站提交/付款；模拟回执不写非 demo confirmed；敏感券码加密。

**不得声称 114/104 全部 done。**

