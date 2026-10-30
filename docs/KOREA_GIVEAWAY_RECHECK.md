# FlightHunter · 韩国免费机票抽奖状态纠错与真实发现测试

- **时间（UTC）**：2026-10-30
- **开发 HEAD**：`3035afc`（其前序 `8bade1b` 状态模型；第三阶段文档 `19a39a1`）
- **测试库**：`%TEMP%\fh_korea_disc\data\korea.db`（隔离）
- **浏览器证据目录**：`data/korea_recheck/`
- **安全**：只读；未报名/未登录提交/未绕过限制

---

## 任务 A · K-SPICY FOOD

**URL**：`https://english.visitkorea.or.kr/svc/sv/surveyIntro.do?srvyKeyCd=a02e295b-2b64-490a-929e-00b97bcc5ff7`

### 真浏览器（Playwright Chromium 1247）

| 项 | 结果 |
|---|---|
| HTTP | 200 |
| 可见文案 | *Read our K-SPICY FOOD article, take the quiz, and enter to win round-trip flights to Korea!* |
| 可见按钮 | **Join Now**（登录后进入 `event.do?id=…`） |
| 隐私条款 | 需勾选同意才能参赛（未勾选、未提交） |
| 截图 | `data/korea_recheck/kspicy.png` |
| 日期 | **页面正文未出现 2026-10-31 或其它起止日期** |
| HTML 模板文案 | 源码含 `No available surveys` / `already participated`，但**非**当前主视图结论；不得据此判已结束 |

### 状态结论

| 字段 | 值 |
|---|---|
| `open_status` | **`pending_verification`** |
| 是否 `historical_closed` | **否** |
| 用户截图截止 2026-10-31 | **未能在官方页文本中复核**；今日 10-30 尚未到该日，更不能判结束 |
| 资格 | **unknown**（非韩国居民限制已记录；无真实用户档案） |
| `can_enter_now` | false（待核实 + 资格 unknown，**不**标已结束） |

**修复**：`open_status_from_dates` + survey 路径强制 `pending_verification`；`ended_flight_rounds` 不再包含日期未知活动。

---

## 任务 B · LOCAL AIRPORT FOOD（韩国地方机场往返机票）

**已知官方 URL**：`https://chinese.visitkorea.or.kr/svc/contents/contentsView.do?dataSetId=286&menuSn=917&vcontsId=1594420`

### B1 自主发现（不注入详情 URL）

| 项 | 结果 |
|---|---|
| 入口来源 | `VISITKOREA 中文美食栏目` → `https://chinese.visitkorea.or.kr/svc/sp/food` |
| 发现方式 | 页面内 `javascript:goLinkPage(... contentsView.do?...vcontsId=1594420)` |
| 自主发现 | **成功** — 候选标题「K-Food 惊喜专栏…」，`official_url` 含 `vcontsId=1594420` |
| 发现路径 | 美食栏目 HTML → goLinkPage → 官方详情 |
| 与核验路径 | **分开记录**（发现≠规则核验） |

### B2 已知 URL + 官方海报核验

| 项 | 结果 |
|---|---|
| 页面 | 200；标题含「韩国往返机票活动」；正文多为海报图 |
| 海报 | `data/korea_recheck/local_airport_poster.png`（1.8MB，官方图床） |
| 海报可读规则 | **活动时间 2026.10.26～2026.11.22**；特等奖地方机场往返机票 **3名×2张**；中奖公布 2026.11.25 |
| 今日 10-30 | **仍在活动期内** → `open_status=open` |
| 入口 | 海报「参与活动」/问答；需按官方流程（未最终提交） |
| 资格字段 | 官方页文本未完整给出居住/国籍细则 → **unknown**（不臆测） |
| `open_flight_rounds` | `["poster_flight_event"]` |
| `can_enter_now` | false（开放中但用户资格 unknown） |

**说明**：媒体所称 10/26–11/22 与**官方海报一致**；日期来自海报人工读出后以 `--poster-facts-json` 写入解析（非注入活动 URL 冒充发现）。

---

## 任务 C · 状态模型修复

| 状态 | 含义 | 判定 |
|---|---|---|
| `open` | 有日期证据且今日在期内 | 仅日期窗口 |
| `closed` | 有日期证据且已过截止 | 仅日期窗口 |
| `pending_verification` | 需登录 / 日期未知 / 仅 Join Now | **禁止当已结束** |
| `unknown` | 无足够证据 | 不进 open_only |

API：

- `open_only=true` → 仅 `open`
- `pending_only=true` → 仅 `pending_verification`
- 用户资格 unknown **不**改变 `open_status`

**实测 API**（隔离库）：

```
open_only+flight_only → 1: [poster_flight_event] LOCAL AIRPORT FOOD
pending_only+flight_only → 1: [survey_roundtrip] VISITKOREA Survey
flight_only → 含上述两条 + 聚合 unknown 线索
```

**测试**：`tests/unit/test_open_status_model.py` 等 → **196 passed**

**提交**：`8bade1b` · `3035afc`

---

## 任务 D · 四类结论（纠正第三阶段表述）

| # | 类别 | 本项目状态 |
|---|---|---|
| 1 | FlightHunter **尚未成功发现** | K-SPICY 自主发现仍 **DISCOVERY_MISSED**（survey 不在 events 列表 API）；此前亦未发现 LOCAL AIRPORT |
| 2 | **已发现但未完整核验** | 多数聚合 flight 线索（Rally House 等）无有效期/官方规则 |
| 3 | **已核实当前开放的免费机票** | **1**：LOCAL AIRPORT FOOD（官方海报日期 + 官方 URL + 自主发现链路） |
| 4 | **已通过真实用户资格审核** | **0**（无真实国籍/居住档案；合成档案仅测规则） |

### 对 `THIRD_LIVE_ACCEPTANCE.md` 的纠正

| 原表述问题 | 纠正 |
|---|---|
| K-SPICY 易被读成不可用/历史 | 应为 **pending_verification**（Join Now + 无官方日期） |
| “真实可参加机票 = 0” 在加入 LOCAL AIRPORT 后 | **可展示开放机票活动 = 1**；但 **真实用户资格通过仍 = 0** |
| 未发现 LOCAL AIRPORT | 经美食栏目 + goLinkPage **已可自主发现** |

---

## 证据与日志

| 路径 | 内容 |
|---|---|
| `data/korea_recheck/kspicy.png` | K-SPICY 浏览器截图 |
| `data/korea_recheck/local_airport_poster.png` | 官方海报 |
| `data/korea_recheck/browser_results.json` | 页面关键词/链接 |
| `data/korea_recheck/web_campaigns_recheck.png` | Web 活动页 |
| `%TEMP%\fh_korea_disc\` | 自主发现与核验配置/DB |

---

## 最终三问（直接回答）

1. **K-SPICY 是否仍开放？**  
   **无法确认已结束 → `pending_verification`。** 页面有 Join Now/登录与问卷隐私步骤；**没有**官方起止日期文本；HTML 里的 “No available surveys” 不足以判结束。用户提供的 10-31 截止**未能在页内复核**。

2. **LOCAL AIRPORT FOOD 是否仍开放？**  
   **是（`open`）。** 官方海报：2026.10.26–11.22；今日 10-30 在期内；奖品 3×2 张地方机场往返机票。

3. **为何之前没发现 / 现在能否正确显示？**  
   - 之前：未解析 `javascript:goLinkPage` 美食栏目链接，也无该详情 URL 注入（正确未注入）。  
   - 现在：**能**通过美食栏目自主发现 1594420；Web/API 分别显示 **open** 与 **pending_verification**，不再把日期未知标成已结束。

Git：`develop` @ `3035afc`，未合并 main，未 push，未自动报名。
