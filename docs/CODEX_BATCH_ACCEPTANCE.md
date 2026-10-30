# FlightHunter · Codex Q1–Q5（R-001~R-017）整改验收

- **日期：** 2026-10-30  
- **基线：** Codex 复验 `32544e4` / R-001~R-017  
- **测试：** **262 passed，1 warning**（原 11 条 GBK 子进程警告已消）  
- **原则：** 不宣称完整 V1.0；不自签关单；不碰正式库 / 不重置 OBSERVATION  

## 对照 Q1–Q5

| 组 | 覆盖 | 落地 | 状态 |
|---|---|---|---|
| **Q1 安全** | R-001, R-002, R-003, R-011 | 每跳**先** URL/DNS 校验再 robots/正文；robots 403/429/异常 **fail-closed**；流式读取超限立即拒；`safe_get_sync` 在已有 loop 中走线程新 loop | **完成** |
| **Q2 语义筛选** | R-004–R-009 | 多金额多目的地不写单一票价；MOP≠HKD；仅发布标签写 published_at；`user_feedback` 与 signal_status 同源；HKG↔PVG 跨境保留；目的地不匹配航司名；time_field 可分 travel/published/found | **完成主路径** |
| **Q3 抽奖/行程** | R-010, R-016 | candidate 不得 core_recommend；排除/国内航段标 excluded_or_domestic；confirm 恢复尊重 `auto_attach_fare_watch_to_new_trip` | **完成** |
| **Q4 通知/来源** | R-012, R-013, R-015, R-017 | `NotificationDelivery` 持久表+迁移 0005；成功跨进程不重复；失败 attempts≤3；`last_result=ok_existing`；pwsh subprocess UTF-8 | **完成** |
| **Q5 迁移** | R-014 | 显式比较 version vs head（in_sync/outdated/no_version）；Web `create_app` 接线告警；默认不自动改正式库 | **完成** |

## 关键回归（本轮）

| 场景 | 结果 |
|---|---|
| public→127.0.0.1 | **无**私网 robots/请求 |
| robots 403 | 不访问目标 |
| 流式 400B / max 100 | response_too_large |
| 台湾800·大阪1500 | 不写单一 reported_total |
| MOP$1500 | currency=MOP |
| 裸日期 2025-01-02 | published_at=None |
| 發佈日期·2026-10-29 | 写入 published |
| feedback=bookmarked | 命中 signal_status |
| HKG→PVG + exclude_domestic | 保留 |
| 目的地=香港 vs 香港航空 | 不误匹配 |
| 国内航班/不包括大陆 | core_recommend=False |
| fare_monitor 关闭 | confirm 不启用 |
| toast 成功后清内存再发 | 不重复 |
| toast 失败×5 | attempts≤3 |
| 0001 vs head | outdated, ok=false |
| 全量 unit | **262 passed** |

## 仍 PARTIAL / NOT_TESTED

| 项 | 说明 |
|---|---|
| 真实 FlyNext 全链路 | 依赖外网时点 |
| 真实桌面 toast | 需人工点验 |
| 72h 连续 / 104 项 | NOT_TESTED |
| 公网 SaaS | 不在 V1 范围 |
| 跨站改写合并 | 仍保守 PARTIAL |

## 三问

**A. 个人日常试用？**  
**更近，仍非正式关单**：SSRF robots 先行、串价、收藏筛选、跨境漏滤、通知重复/无上限、旧库误报最新、异步 AJAX 丢失已修主路径；真实网络/桌面/长跑仍待 Codex 与用户。

**B. Codex 独立复验？**  
**0 / 待复验**。262 测试 ≠ 关单。

**C. 完整 V1.0？**  
**未宣称**。104 项、72h、公网不在本轮。

## 交付

- 代码：本批 `fix(codex-q1-q5)`  
- 迁移：`0005_notification_delivery`  
- 回归：`tests/unit/test_codex_q1_q5.py`  
- 建议复验快照：`git archive HEAD`  

**不宣称** Codex 已 PASS。
