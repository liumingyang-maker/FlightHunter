# FlightHunter · 亚洲来源 + 全球错价 + 四频道验收

- **HEAD：** 见文末（开发中更新）  
- **基线：** `37292ed` 为祖先；未回退业务价值结论  
- **备份：** `backups/*_133247.bundle` · daily DB copy  
- **Worker：** 单实例锁仍 alive；观察 started_utc **未重置**  
- **测试：** 216 passed  

---

## 1. 四频道（统一库，严格分流）

| 频道 | 实测 primary | 折叠 | 说明 |
|---|---:|---:|---|
| 我的出发地 | **1** explicit（TFU-HEL） | **11** 全国/待核实 | 宽泛新闻不进主列表 |
| 全国出发 | **17** | 0 | 内地机场/全国线索 |
| 香港／澳门 | **0** | 0 | 本轮无港澳信号（如实） |
| 全球错价 | **0** | 0 | 本轮无 bug/fare 类入库（如实） |

Playwright：`data/daily_usage/ui4/ch_*.png` · `ch_mobile.png`（4 个 tab 移动端可见）

**边界：** 美国 bug fare 仅进 D；全国多地不进 A 主列表；HKG 不进全国。

---

## 2. 来源池

- fare 来源注册 **17** 个（含 MainlyMiles、Flyday.hk、The Flight Deal、Error Fare News 等）  
- 历史成功读取约 **11**  
- robots/403：Secret Flying、Fly4Free、部分 Google News 等 **如实失败**  
- 新增信号累计约 **24**（daily 库）

详见 `docs/FARE_SOURCE_REGISTRY.md`。

---

## 3. 去重 / 通知 / 运行

- 跨源合并：`merge_intel_signals`（同一 event 多链接）  
- 四频道共用 signal_id，不重复通知事件  
- Worker 1800s · 锁心跳正常 · 启动项同配置  

---

## 4. 未完成 / 零结果（诚实）

1. 港澳频道本轮 **0** 条有效信号（源已注册，待持续抓取）  
2. 全球错价频道本轮 **0** 条（错价 RSS/站多 robots）  
3. 明确匹配城市仍以 **1** 条为主（与此前基线一致，未虚假抬高）  
4. 未引入 RSSHub/changedetection 常驻服务（避免复杂度）  

---

## 5. 最终四问

| 问题 | 答案 |
|---|---|
| 监控多少活跃有价值来源？ | 注册 17；**历史成功读取 ~11**；持续有价值≈smzdm×2 + OMAAT + VFTW 等 |
| 近 7 天中国内地相关国际机票？ | daily 库 **~24** 条信号（多为全国多城） |
| 港澳？ | **0**（源已挂） |
| 全球 Bug/Fuel Dump 来源？ | 注册 Google News Error Fare、Secret Flying、Fly4Free、The Flight Deal 等；**成功抓取有限** |
| 四频道是否分流？ | **是**（A 主列表仅 explicit；D 仅错价；B 排港澳） |
| 无付费 AI 可运行？ | **是** |

Git：`develop` @（见 commit）· 未 push · 未合并 main。
