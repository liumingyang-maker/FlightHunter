# FlightHunter · 真实来源激活与四频道有效产出验收

- **HEAD：** `f2f86c5`  
- **关系：** `ff0bd07` ⊂ `0565e3b` ⊂ `f2f86c5`  
- **测试：** 221 passed · ruff 通过  
- **Worker：** 原锁/观察起点未重置  
- **备份：** 此前 `backups/*_133247.bundle` 仍有效  
- **诊断产物：** `data/daily_usage/source_diagnostics.json`

---

## 1. 17 来源中真正稳定产出有效情报的有哪些？

| 来源 | 本轮状态 | 情报产出 |
|---|---|---|
| 什么值得买 · 每日机票推荐 | active · 历史 valuable | **高**（全国多城国际） |
| 什么值得买 · 国际机票 | active | 有 |
| 北美票帝 | active | 有（中美） |
| **FlyNext.hk** | **ok_valuable** | **4 条香港出发线索（HKD）** |
| One Mile at a Time / VFTW | active RSS | 有（全球，非港澳） |
| SingPromos | 曾 valuable | 有（新加坡，误解析 OFF/DBS 已知噪声） |
| The Flight Deal / MainlyMiles / Premium-Flights | ok_zero | 读取成功但本轮 0 解析 |
| Travel-Dealz | 曾 failed → RSS `/rss` | 本轮 0（连接超时后） |
| Flyday.hk | **403 manual_only** | 0 |
| Secret Flying / Fly4Free / 部分 Google News | failed/robots | 0 |

**真正稳定产出：** smzdm 每日/国际、北美票帝、**FlyNext**、OMAAT、VFTW。

---

## 2. Fly Next / Flyday 此前为何 0 产出？

| 源 | 原因 | 修复 |
|---|---|---|
| FlyNext | 列表在首页 `/blog/`，标签含繁体機票/HK$ 但结构化解析过严；无 RSS | **已修**：blog 链接 + HK$ + 機票关键词；**已入库 4 条** |
| Flyday | **HTTP 403**（分类页/feed） | 保持 **blocked/manual_only**，**不绕过** |

---

## 3. 港澳频道能否显示真实近期香港出发促销？

**能（基于 FlyNext 真实文章）。**

- 港澳频道 primary：**≥2**（Peach 大阪 HK$1600、国泰×渣打 11.11 等）  
- 出发地：**HKG**（非仅标题出现香港）  
- **上海→香港** 不进港澳出发主列表  
- **香港航空上海出发** 不因航司名含香港而归入港澳  

截图：`data/daily_usage/ui4/hk_after_activation.png`

---

## 4. Travel-Dealz / FlyerTalk / Premium-Flights

| 源 | 结果 |
|---|---|
| Travel-Dealz | **已改** `travel-dealz.com/rss`（`/feed` 超时）；本轮 **0 文章**（连接问题），通道合法 |
| Premium-Flights | **RSS 可读** `premium-flights.com/feed/`；本轮 **0 解析** |
| FlyerTalk | **未接入**（论坛登录/条款限制，未假定镜像合规） |

---

## 5. 全球错价频道

- 本轮 **0 条** 真实 error/fuel dump 入库  
- 原因：错价专业站 robots/连接限制 + 当前无入库文章  
- **不是**把普通商务舱低价硬塞进错价频道  

---

## 6. 四频道误分类与重复

- 频道路由单测 + 港澳边界单测通过  
- 同 signal 多频道共用 ID  
- 全国待核实不进「明确匹配」主列表  

---

## 7. 真正按「发布日期」统计（24h/7d）

| 区域 | 24h 新发布（DB published_at） | 说明 |
|---|---:|---|
| 中国内地相关 | **0～少量** | 多数社区源 **无 published_at**，仅有系统发现时间 |
| 港澳 | **2～4**（FlyNext 2026-10-29/30 标题日期） | 部分仅在标题中 |
| 全球错价 | **0** | 无 |

**不得**把「今天首次抓取」算成「今天新发布」。

---

## 8. 真实网站 vs Mock

| 能力 | 真实网络 |
|---|---|
| FlyNext 列表发现+入库 | **是** |
| 港澳频道 HKG 出发展示 | **是** |
| Flyday | 403 阻断 **如实** |
| Travel-Dealz/Premium RSS 发现 | 通道合法；本轮 0 条 |
| 四频道分流 Playwright | **是** |

---

## 9. 最终七问

1. **稳定产出来源：** smzdm×2、北美票帝、**FlyNext**、OMAAT、VFTW  
2. **FlyNext/Flyday 原因：** 解析过严 / 403  
3. **港澳频道真实近期促销：** **能**（FlyNext Peach 等）  
4. **Travel-Dealz/FlyerTalk/Premium：** Travel-Dealz RSS+Premium RSS **已合法挂接**；FlyerTalk **未接**  
5. **全球错价：** **0 条真实近期**；来源受限+无内容  
6. **误分类/重复：** 边界已测；共用 signal_id  
7. **24h/7d 真正发布：** 港澳约 2–4；内地发布日期多缺失；错价 0  

Git：`develop` @ `f2f86c5` · 未 push · 未合并 main。
