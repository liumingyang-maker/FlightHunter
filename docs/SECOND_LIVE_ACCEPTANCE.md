# FlightHunter 第二阶段实机验收报告（SECOND_LIVE_ACCEPTANCE）

- **时间（UTC）**：2026-10-30
- **开发 HEAD（验收代码）**：`20eee26`（及其前序 `5c3a9e0`）
- **隔离运行目录**：`data/live_tests/20261030_084405/`
- **环境**：PowerShell 7（pwsh）· 独立 SQLite · 12 公开来源种子
- **安全**：未自动报名/付款/领券/建外站账号；未绕过 robots（Contest Girl Daily 明确拒绝后停用）

---

## 0. 韩国 VISITKOREA「K-SPICY FOOD 往返机票」案例

### 已知官方目标（用户指定，未注入来源库/候选库）

| 项 | 结果 |
|---|---|
| 官方 URL | `https://english.visitkorea.or.kr/svc/sv/surveyIntro.do?srvyKeyCd=a02e295b-2b64-490a-929e-00b97bcc5ff7` |
| 页面读取 | **成功**（HTTP 200，`raffle-rules-check` EXIT=0） |
| 官方域名 | `visitkorea.or.kr` → `official_domain_ok=true` |
| 奖品文本 | **含往返机票**（`prize_is_flight=true`）；文案含 *enter to win round-trip flights to Korea* |
| 报名方式 | **survey_quiz**（问卷/答题） |
| 同行者 | 文本提及 companions（赢家侧信息收集） |
| 通知 | 获奖者邮件通知；未在时限内回复可被顺延 |
| 资格 | **unknown**（无用户国籍/居住档案；页面出现 “residents of Korea” 片段，不得臆测为符合） |
| 活动当前有效 | **unknown / 不可确认仍开放**（页面出现 “No available surveys”；日期未结构化解析） |
| 分层结论 | 页面成功读取 ≠ 官方活动仍有效 ≠ 用户 eligible |

**注意**：此前记录的 2026-09-15～2026-10-31 **未能在本次官方页文本中重新核实到完整日期区间** → 记为 `dates_unparsed`，禁止写成已确认仍有效。

### 指标一：自主发现率（不喂官方 URL）

| 项 | 结果 |
|---|---|
| 是否把上述 URL 写入来源库 | **否** |
| 是否手动创建候选冒充发现 | **否** |
| 发现路径 | 来源 `VISITKOREA EN 首页` → 解析到活动 AJAX 端点 `getContentsList.do` → 分页 JSON → 候选入库 |
| 搜索/发现词 | flight / round-trip / survey / quiz / food / giveaway / win |
| 时间 | 2026-10-30T00:45～00:46Z（隔离库） |
| **指定 K-SPICY 活动** | **DISCOVERY_MISSED** |
| 原因 | 该 survey 仅存在于 `surveyIntro.do?srvyKeyCd=…`；**不在** 公开 `getContentsList.do` 活动列表 JSON 中（列表无该 srvyKey）。首页 “VK Events” 为 `javascript:fn_goMenuPage`，静态 href 无具体活动。 |
| 同族真实发现 | 已从 VISITKOREA **官方站**自主发现 **6** 条带 `official_url` 的活动，含：`2025 Last Chance to Win: Round-trip Ticket to Korea`（category=`flight_giveaway`）、`K-Food Quiz`、`No.1 K-FOOD Test` 等（多数 `endYn=Y` 已结束，仍作官方线索保留） |
| 算法改进（已落地） | ① 解析 `javascript:fn_goMenuPage('/path')`；② `official_tourism_board` 来源自动发现并请求 `getContentsList.do` JSON；③ 旅游局同域详情写 `official_url`（保持 `candidate`，不自动 verified） |

**自主发现率（针对指定 K-SPICY 案例）= 0%（DISCOVERY_MISSED）**  
**自主发现率（针对 VISITKOREA 站内可列表化的真实旅行/机票类活动）= 有产出（6 条官方 URL 级候选，含 ≥1 条 flight_giveaway）**

### 指标二：官方核实完成率

| 层级 | 数量 | 说明 |
|---|---:|---|
| 已知 URL 页面快照/规则解析 | 1 | `raffle-rules-check` 结构化输出（本报告 §0） |
| 隔离库 `official_url` 非空候选 | **6** | 全部 VISITKOREA 同域详情页 |
| `official_page_snapshot` 证据 | **1** | 二阶段溯源写入 |
| `aggregator_page_snapshot` 证据 | **7** | 聚合站线索 |
| `verify_status=verified` | **0** | **未**把官方页存在等同 verified |
| 官方规则字段完整（日期+资格+免费） | **0 完整** | K-SPICY：日期未解析；免费条件未命中明确 “free entry” 句 |

**官方核实完成率（页面级）**：指定 URL 读取成功 100%  
**官方核实完成率（规则字段完整到可支撑 eligibility）**：**0%**（保持诚实 partial）

### 指标三：可参与机会数

| 条件 | 结果 |
|---|---|
| 有明确有效期且当前仍开放 | **0**（VISITKOREA 可列表活动多为 `endYn=Y`；K-SPICY 页显示 survey 不可用） |
| 有官方证据 | 有线索，但不足以支撑 “当前可报名” |
| 通过用户资格评估 | **0**（无档案；eligibility=unknown） |
| **可参与机会数** | **0** |

---

## 1. 三条业务主线（隔离库 `20261030_084405` 累计）

### A. 全球免费旅行抽奖：**partial**（全球扩展已生效）

| 指标 | 值 |
|---|---:|
| 真实候选 | **26** |
| 含 `official_url` | **6** |
| `flight_giveaway` | **6** |
| `travel_package_unknown_air` | **4** |
| `lodging_or_cruise` | **3** |
| `other_giveaway`（车/现金等） | **13** |
| 聚合证据 / 官方页证据 | 7 / 1 |
| verified | 0 |
| 自动报名 | 0 |

**其他国家样例（非日本）**  
- **韩国**：VISITKOREA Round-trip Ticket / K-Food 系列（官方 URL）  
- **美国/全球聚合**：Sweepstakes Today Travel 分类 — Myrtle Beach 家庭度假、Bondi 行、Big Ten 门票旅行包、Celebrity 邮轮、Kraft Heinz 等（多数仍为聚合线索）  
- **robots**：Contest Girl Daily 列表 → `robots.txt 不允许抓取` → 失败分类 `robots`，未绕过；来源置 `consecutive_failures`（未改 manual_only 因非 SOURCE_FETCH_DENIED 路径需人工复核）

### B. 日本 Trip Benefits：**partial**

| 指标 | 值 |
|---|---:|
| 福利候选 | **5** |
| 中文指南 | 由 `jp-benefits-scan` 生成（含【待核实】） |
| 确认领券 | **0** |
| 卡包写入 | **0** |
| 演示行程 | 1 条，显著 `demo_only` |

### C. 低价机票雷达：**partial**（情报模式）

| 指标 | 值 |
|---|---:|
| 信号 | **18** |
| 过期促销过滤 | 已启用 |
| 金额/¥ 解析 | 已启用 |
| `urgent_verified` | **0** |
| 实时可购报价 | **无**（未配置授权供应商） |
| 偏好 | 配置默认 CKG/TFU/CTU、双人 — **无授权查询通道**，保持 `price_unconfirmed` |

---

## 2. 独立监控结果

| 项 | 值 |
|---|---|
| 本次运行 `run_id`（目录） | `20261030_084405` |
| 来源总数 | 12（种子扩展后） |
| 来源已抓取 | 12 |
| 任务：completed | 多轮 discover/provenance/jp-benefits |
| 任务：partial | 1（raffle 批：1 来源 robots 失败） |
| 任务：skipped(cooldown) | 1（冷却重扫，**不再计入 task_failures**） |
| 任务：blocked | 0 |
| 心跳 | `monitor.py` metrics 连续写入；断档 >300s 规则已加 |
| 告警样例 | `EXECUTION_PARTIAL_OR_FAILED`（partial 批）；`SOURCE_DENIED_OR_THROTTLED`（robots） |
| 产物 | `events.jsonl` · `alerts.jsonl` · `RESULTS.md` · `logs/step1_*.log` · `step2_rules_check.log` · 浏览器截图 |

**来源失败分类**  
- `robots`：Contest Girl Daily Sweeps  
- `manual_only`：Japan National Tourism Org（抓取失败后策略收紧，未伪造内容）  
- 冷却跳过：预期行为，非失败  

---

## 3. 缺陷清单

| 状态 | 问题 | 证据 / 位置 |
|---|---|---|
| 已复现并修复 | CLI 冷却重扫记 `blocked` 误报失败 | `app/cli.py` → `skipped` + `reason=cooldown_or_no_due_source`；monitor 拆分 `task_failures` / `task_skipped_cooldown` |
| 已复现并修复 | RESULTS 写「暂无监控记录」但 alerts 有内容 | `_first_live_test/export_results.py` 分文件存在/空/有内容 |
| 已复现并修复 | 抽奖导航噪声、机票攻略噪声 | `html_fetcher.py` + `test_live_run_quality.py` |
| 已复现并修复 | 日本福利标题重复（双路径） | URL 规范化去重 `materialize_trip_offer` / `jp_benefits` |
| 已复现并修复 | 活动页列错位、无线索链接 | `campaigns.html` + `pages.py` + API `source_list_url` |
| 已复现并修复 | 官方旅游局静态页看不到活动列表 | `discover_official_tourism_events` + JS 路径解析 |
| 已复现并修复 | 车辆/现金误分类 | `parse_raffle_label` → `prize_other` |
| 已复现并修复 | 过期促销进信号 | 含「过期」拒绝 |
| 已复现未根治 | **指定 K-SPICY 活动自主发现** | DISCOVERY_MISSED：仅 survey 链接，不在 contents 列表 API；需后续支持搜索索引/sitemap/survey 专用通道（**未**用已知 URL 补录冒充成功） |
| 仍受阻 | 实时票价供应商 | 无授权 → 情报模式 |
| 仍受阻 | Contest Girl 明细页 | robots 拒绝，不绕过 |
| 仍受阻 | 用户资格评估 | 无档案保持 unknown |

**回归**：`pytest tests/unit` → **186 passed**；`ruff` 相关 app 路径通过。

---

## 4. 测试与浏览器证据

| 类型 | 位置 |
|---|---|
| 单元测试 | 186 passed（含第二轮质量回归） |
| 自主发现日志 | `logs/step1_autonomous_raffle.log`（raffles=12/8/6） |
| 官方规则解析 | `logs/step2_rules_check.log` |
| Sweep | `logs/sweep.log` 全 EXIT=0 |
| Web API | `/api/v1/ops/status|campaign-rounds|benefits|fare-deals|trips` = 200 |
| 首页 vs API | 真实行程 **0** / 演示 **1** 一致 |
| Playwright 截图 | `browser_campaigns.png`（含 visitkorea「官方页」链接）· `browser_fare.png` · `browser_trips.png` |
| migrate --config | 指定临时配置生成 `custom.db`，不误写 snapshot 库 |

---

## 5. 用户可执行动作（当前真实能力）

1. 打开 Web `http://127.0.0.1:8765/` → 「找机会」：按标题/链接查看韩国 VISITKOREA 官方详情与聚合线索。  
2. 对可列表化的 VISITKOREA 活动：查看官方 URL、分类（机票/其他）、证据类型。  
3. 日本行程：查看 unconfirmed 福利与【待核实】中文指南；**不可**当作已领券。  
4. 机票：查看社区爆料分层；无供应商前不得当可购价。  
5. CLI：`raffle-rules-check <official_url>` 只读核验官方规则。

---

## 6. 总评（不粉饰数字）

- **指定 K-SPICY 案例自主发现：DISCOVERY_MISSED**（原因可复核；算法已能发现同站可列表化机票/食品类官方活动）。  
- **已知 URL 官方核验：页面与奖品/报名通道解析成功；日期与当前开放状态未证实；资格 unknown。**  
- **全球扩展：成功**（韩国官方旅游局 + 美国/澳洲等聚合旅行抽奖；分类含 flight/package/lodging/other）。  
- **可参与机会数：0**（无“仍开放 + 规则完整 + 资格通过”三者同时满足的活动）。  
- 未合并 `main`，未 push，未上传密钥/Cookie/完整私人库。

**Git HEAD（报告时）**：`20eee26` + 本报告文档提交（见 `git log`）。
