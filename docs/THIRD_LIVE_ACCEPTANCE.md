# FlightHunter 第三阶段实机验收报告（THIRD_LIVE_ACCEPTANCE）

- **时间（UTC）**：2026-10-30
- **开发 HEAD（报告时）**：`27bbac8`（其上为 `b605cfb` 多轮次功能；第二阶段文档 `9a06807`）
- **隔离运行**：`data/live_tests/20261030_090436/`
- **环境**：PowerShell 7 · 独立 SQLite · 12 来源
- **安全**：只读核验；未报名/付款/领券/绕过 robots

---

## 0. 工程一致性说明

### 为何第二阶段报告写 `20eee26`，最终汇报是 `9a06807`？

| 提交 | 含义 |
|---|---|
| `20eee26` | 第二阶段**功能代码**（旅游局 JSON 发现、规则 CLI 等）提交时写入报告正文的 HEAD |
| `9a06807` | 随后单独提交的 **`docs/SECOND_LIVE_ACCEPTANCE.md` 文档**；“最终汇报 HEAD”指文档落地后的仓库 HEAD |
| `b605cfb` / `27bbac8` | 第三阶段多轮次拆分与 open 过滤修复 |

二者是同一 develop 时间线上的先后提交，**不是回退或覆盖**。

### 失败的字符串替换（`result.text or ""`）

- 期望补丁：`parse_*` 调用写成 `result.text or ""`。
- 实际源码：`if result.ok and result.text:` 守卫内使用 `result.text`（非 None）。
- **判断**：原修复意图（防 None）在守卫下已隐含生效；为一致与防御，已在 `parse_raffle` / `parse_trip` / `parse` 处改为显式 `result.text or ""`（`b605cfb`）。
- **边界测试**：`tests/unit/test_third_live_rounds.py::test_fetch_source_with_none_text_does_not_crash`（`text=None` 的 FetchResult 不崩溃）。

未使用整段模糊替换；改动为读源码后的精确编辑 + diff 提交。

---

## 1. 三层发现能力（禁止混算）

| 层级 | 定义 | 本轮结果 |
|---|---|---|
| L1 全球自主发现 | 无活动名/URL 提示 | VISITKOREA 列表 JSON + Sweepstakes Travel → **多条**旅行/机票候选入库（raffle 累计 31） |
| L2 定向搜索发现 | 知活动名不知 URL | 未做搜索引擎注入；同站列表可命中历史 K-Food / Round-trip 标题 |
| L3 已知 URL 核验 | 给官方链接解释规则 | **案例 A/B/C 完成**（见下） |

---

## 2. 三个 VISITKOREA 独立回归

### A. K-SPICY FOOD 问卷抽往返机票（历史/核验）

| 项 | 结果 |
|---|---|
| URL | `.../surveyIntro.do?srvyKeyCd=a02e295b-...` |
| 页面读取 | 成功 |
| 奖品 | 含 round-trip flights（文本） |
| 通道 | survey_quiz |
| 日期 | **未解析** → `dates_unparsed`；页面曾出现 survey 不可用文案 |
| 资格 | **unknown**（无档案） |
| 自主发现 | **DISCOVERY_MISSED**（不在 contents 列表 API；未注入 URL 冒充发现） |
| 标注 | **历史/不可用核验回归**，非当前可参加成果 |

日志：`logs/case_a_rules.log`

### B. VISITKOREA Exclusive Launch Event（多轮次拆分）— **核心通过**

URL：`.../contentsView.do?vcontsId=1591568`  
时间锚点（实机 now）：`2026-10-30`

| 轮次 | 奖品 | 日期 | active_now | 可参赛? |
|---|---|---|---|---|
| `previous_event_flight` | **往返机票** | 2026-07-20～**08-19** | **false** | 否（历史） |
| `current_period_1` | 随机礼券等 | 07-20～08-31 | false | 否 |
| `current_period_2` | 礼券等 | 09-01～09-30 | false | 否 |
| `current_period_3` | **Gift Voucher** | 10-01～**10-31** | **true** | 是（但**不是机票**） |

**防拼接验证**：不存在「Event1 机票 + Event2 截止 10-31」被标成仍开放的机票轮。  
`open_flight_rounds=[]`；`ended_flight_rounds=[previous_event_flight]`。  
合成档案 CN/30：机票历史轮规则资格可 pass，但 **active=false → can_enter_now=false**。  
非韩国公民限制已写入各轮 `residency_restriction`。

日志：`logs/case_b_multi.log` · 入库 edition：`prev_flight / cur_p1 / cur_p2 / cur_p3`

### C. K-Local Food Hunters 33 — **结束机票不进开放列表**

URL：`.../vcontsId=1593009`

| 项 | 结果 |
|---|---|
| 奖品 | Round-trip Ticket（3 winners，两人/人）+ Amazon 礼品卡 |
| 日期 | 2026-08-27～**10-06** |
| active_now（now=10-30） | **false** |
| open_flight_rounds | **[]** |
| DB | edition `single_flight`，closes 2026-10-06，active=false |
| Web/API | `flight_only` 可见该历史条目且 `open_now=false`；`open_only&flight_only` 不含它 |

日志：`logs/case_c_food.log`

### 合成资格档案说明

- 使用 **明确标注的合成档案**（nationality=CN, residence=CN, age=30）检验规则分支。  
- **不冒充真实用户资格**；真实用户无档案时保持 `unknown`。  
- KR/KR 档案 → ineligible（非韩国公民限制冲突）。

---

## 3. 当前真实可参加机会（诚实）

| 条件 | 数量 |
|---|---:|
| 官方多轮机票且 active_now=true | **0** |
| 有明确有效期的聚合 flight 线索被当作开放 | **0**（`open_only` 已禁止无日期=开放） |
| 规则完整 + 仍开放 + 用户 eligible | **0** |

**真实可参加机票抽奖 = 0。**  
B 页当前开放的是 **礼券期**，不是机票。C 与 A 均不可报。聚合站无截止日期线索不得计入开放。

---

## 4. 日本优惠 / 机票雷达（并行）

### 日本

- `jp-benefits-scan`：Time Out 列表 → 福利候选 + 中文【待核实】指南。  
- 分类：`free_admission_info` / listing 区分已加；**无券码不写卡包**。  
- 官方场馆三窗（领/约/用）完整闭环：**仍 partial**（未完成单一官方商家全字段核实）。  
- 隔离库 benefits_real=5，confirmed=0。

### 机票雷达

- 过期促销过滤、¥/K 价格解析已启用。  
- 信号 18；**无授权供应商** → 全部 `price_unconfirmed`；**不标 urgent_verified**。  
- 重庆/成都双人偏好：配置默认存在，**无合法实时报价通道**，不伪造。

---

## 5. 监控分层（本次 run）

| 指标 | 值 |
|---|---:|
| 来源总数 | 12 |
| 成功读取 | 12 |
| robots 拒绝 | 1（Contest Girl Daily） |
| 本次/累计候选（隔离库 raffle） | 31 |
| multi_round 轮次 | 5 |
| official_url 非空 | 11 |
| official 证据 | 2 |
| open_flight_strict（active+flight） | **0** |
| task partial | 1（robots） |
| 产物 | `events.jsonl` / `alerts.jsonl` / `RESULTS.md` / case_*.log / `browser_campaigns.png` |

HTTP 200 / EXIT=0 **不等于**业务可参加。

---

## 6. 已修复问题（本轮）

1. HEAD 说明与 `result.text` 防御式补丁 + None 测试  
2. 多轮次拆分：日期与奖品绑定本轮；防机票/礼券日期拼接  
3. API `open_only`：无明确有效期不得视为开放  
4. `can_enter_now` = active ∧ eligible（历史回归单独标注）  
5. 多轮次物化入库（edition_key）供 Web 展示  

**测试**：`pytest tests/unit` → **190 passed** · ruff 通过

---

## 7. 用户操作入口

1. Web `http://127.0.0.1:8765/campaigns`：可见 `[previous_event_flight]`、`[single_flight_event]` 等，关闭活动 `open_now=false`。  
2. API：`GET /api/v1/campaign-rounds?open_only=true&flight_only=true`  
3. CLI：`raffle-multi-round-check <url> --nationality CN --residence CN`  
4. 官方链接可点；仍禁止自动提交。

浏览器截图：`data/live_tests/20261030_090436/browser_campaigns.png`

---

## 8. 未完成 / 阻塞

| 项 | 原因 |
|---|---|
| 当前开放且规则完整的免费机票 | 官方列表无；不得造假 |
| K-SPICY 自主发现 | 不在公开 events JSON |
| Contest Girl 明细 | robots 拒绝 |
| 实时票价 | 无授权供应商 |
| 日本单一官方福利全窗口 | 仍 partial |

---

## 9. 【2026-10-30 纠正】韩国活动状态（见 `docs/KOREA_GIVEAWAY_RECHECK.md`）

| 活动 | 旧结论风险 | 纠正后 |
|---|---|---|
| K-SPICY FOOD | 易被读成不可用/历史 | **`pending_verification`**（Join Now+登录；无官方日期；禁止 historical_closed） |
| LOCAL AIRPORT FOOD | 未发现 | **自主发现成功** + 海报核实 **`open`**（10/26–11/22，3×2 机票） |
| 真实可参加机票 | 曾写 0 | **可展示开放=1**；**真实用户资格通过仍=0** |

第三阶段 “真实可参加机票抽奖=0” 在加入 LOCAL AIRPORT 后应改为：**系统可展示的已核实开放免费机票活动=1；已完成真实用户资格审核=0**。

---

## 10. 总评

**第三阶段真正新增能力：**  
同页多活动/多期 **拆分规则引擎** + 入库 edition + Web/API 开放过滤 + 合成资格三态 + 可参赛判定。  

**验收案例 B/C 已证明：** 机票轮与礼券期分离；已结束机票（10-06）不进开放列表。  

**真实可参加机票抽奖仍为 0**——如实报告。  

Git：`develop` @ `27bbac8`，未合并 main，未 push。
