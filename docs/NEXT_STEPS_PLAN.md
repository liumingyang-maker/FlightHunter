# FlightHunter 下一步详细方案清单

**基线：** `5be9c65`（develop，Worker 已修 fare 周期抓取）  
**目标：** 个人测试版可日用 + 覆盖明显短板  
**原则：** 不造假数据；不自动购票/报名；不绕 robots；正式库授权后才迁移  

---

## 0. 当前状态快照（2026-10-31）

| 项 | 状态 |
|---|---|
| Web | ✅ `:8765` 运行中 |
| Worker | ✅ PID 16440，已含 **fare 周期抓取** |
| fare 来源 | 20 个（active 11 / manual 9） |
| 库内情报 | ~28 条 |
| 单测 | 347+ passed |
| 72h 监控 | 后台采样中 |
| 104 矩阵 | 67 PASS / 37 NOT_TESTED |

**已修关键 bug：** Worker 原先只扫行程订阅、不抓 fare → 已修。

---

## 1. P0 · 本周必做（可靠日用）

### 1.1 验证 Worker 真在出货
- [ ] 观察 1–2 个周期后 `source-health`：active 源 `last_attempt_at` 是否更新
- [ ] `discover --execute` 手动跑通 3 个 active 源
- [ ] 确认 `last_fare` 心跳字段持续 >0
- **验收：** FlyNext/什么值得买 至少 1 个在 6h 内有新 attempt

### 1.2 修通 3 个最有价值的 manual_only
| 优先 | 源 | 方向 |
|---|---|---|
| 1 | Flyday.hk | 检查 403/robots/Cloudflare；改 UA/延迟；仍失败则保持 blocked |
| 2 | Google News · 国际特价机票 | RSS 可用性；失败则调整查询或 timeout |
| 3 | SingPromos Airlines | 同上 |

- **验收：** 至少 1 个从 manual → active 且成功抓取一次；或明确 BLOCKED 证据

### 1.3 迁移版本对齐（daily_usage）
- [ ] 备份 `data/daily_usage/fh_daily.db`
- [ ] `python -m alembic upgrade head` → 0005
- [ ] `doctor` 显示 `in_sync`
- **注意：** 正式库；你授权后我再执行，或你本地跑

### 1.4 真实 toast 抽测（需你桌面 2 分钟）
- [ ] 触发一条通知 → toast 出现
- [ ] 重启 Worker → 同一事件不再弹
- **验收：** 记入 72h 报告

---

## 2. P1 · 覆盖提升（测试版核心价值）

### 2.1 新增来源（建议 5 个，稳定优先）

| # | 源 | 理由 | 类型 | 风险 |
|---|---|---|---|---|
| 1 | **Secret Flying RSS**（若可用） | 比 HTML 稳 | RSS | 低 |
| 2 | **FlyerTalk Deals / Mileage Run** | 全球促销 | RSS/HTML | 中 |
| 3 | **日本：ANA/JAL 官方促销新闻页** | 补日韩 | 官方 HTML | 中（JS 风险） |
| 4 | **韩国：济州航空/大韩促销**（公开页） | 补韩国 | 官方 | 中 |
| 5 | **携程/去哪儿 公开特价页**（若 robots 允许） | 内地补充 | HTML | **高** robots |

**更稳妥的替代（优先做）：**
| 替代 | 说明 |
|---|---|
| MainlyMiles RSS（若有） | 已有 HTML，补 feed |
| The Points Guy feed | 已知有 feed |
| God Save The Points / OMAAT 补充 | 英文 deal |
| 飞猪/同程 **仅当** robots 明确允许 | 否则 BLOCKED |

**实施顺序：** 先 RSS（低风险）→ 再官方公开页 → 内地 OTA 默认不做。

### 2.2 四频道体验补齐
- [ ] 目的地筛选空状态文案
- [ ] 多价情报卡片：列出各价 + 原文链接（已有 multi_price 标记）
- [ ] 收藏后「已收藏」筛选回归 Playwright 点验
- **验收：** 四频道切换 + 筛选 e2e 截图

### 2.3 抽奖来源（P2）
- [ ] VISITKOREA 继续 auto_verify
- [ ] 增加 1–2 个官方旅游局公开活动页（仅线索，不自动报名）
- [ ] core_recommend 保持保守，无国际证据不标 core

---

## 3. P2 · 工程债（不挡日用，挡“完整 V1”）

| # | 项 | 动作 | 估时 |
|---|---|---|---|
| 1 | 浏览器连接 IP 绑定 | 标 partial；真外站 MANUAL_ONLY | 0.5d |
| 2 | 跨源合并 | 保持保守；UI 显示多来源 | 1d |
| 3 | 通知 exactly-once | 文档 at-most-once；可选 outbox 表 | 1d |
| 4 | httpx 私有 API | 锁版本 + 升级 checklist | 0.5d |
| 5 | 104 矩阵 37 项 NOT_TESTED | Playwright/隔离测补证据 | 1–2d |

---

## 4. 验收与发布节奏

```text
Day 1     1.1 验证 Worker 出货 + 1.2 修 1 个 manual 源
Day 2-3  2.1 加 2–3 个 RSS 源 + 实测
Day 3    1.3 迁移升级（授权后）+ 1.4 toast
Day 4-5  2.2 四频道 e2e + 矩阵补 10–15 项
Day 6-7  72h 报告汇总 + 交 Codex 一轮
```

**个人测试版 DoD（再确认）：**
1. Worker 每轮有 fare 抓取证据  
2. 至少 12 个 active 源在 24h 内有 attempt  
3. toast 不重复  
4. 72h 连续（或等时长采样）  
5. 104 矩阵无新增 P1 FAIL  
6. Codex 一轮无新安全 P1  

---

## 5. 明确不做（本阶段）

- 实时报价 API  
- 自动购票/报名/付款  
- 公网上线 / 多用户  
- 大规模爬取受 robots 限制的站点  
- 重写架构  

---

## 6. 我接下来马上能做的（你点头我就干）

| 优先级 | 任务 |
|---|---|
| A | 修 Flyday / Google News 其一到 active 或标 BLOCKED |
| B | 接入 2 个稳定英文 RSS（The Points Guy 等） |
| C | Playwright 四频道 + 收藏筛选 e2e |
| D | 补 104 矩阵 15 项证据 |

**建议顺序：A → B → C → D。**  
你现在说「做 A」或「都做」即可。
