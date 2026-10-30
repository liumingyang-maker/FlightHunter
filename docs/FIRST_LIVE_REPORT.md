# FlightHunter 首次真实运行报告（FIRST_LIVE_REPORT）

- **报告时间（本地）**：2026-10-30
- **测试基线（用户指定）**：`1d69efb`（项目已前进，未回退；在 `develop` 上取当时 HEAD 实测）
- **最终代码 HEAD（修复后）**：见 `git log`（含 `4b495d4` / `84590f3` 等实机修复提交）
- **运行目录**：`data/live_tests/20261030_010245/`（隔离 snapshot + 独立 SQLite）
- **规则**：全程使用 **PowerShell 7（pwsh）**；未购票/付款/报名/领券；未绕过 robots/CAPTCHA；无账号令牌上传

---

## 1. 测试是否成功启动

| 项 | 结果 |
|---|---|
| 工具包 `_first_live_test` | 已安装；`1_start.ps1` / `run_sweep.ps1` 已适配 pwsh 与当前 HEAD |
| `Run-Stage` 数组参数 | 实测通过（`@Arguments` splat 正确） |
| 隔离迁移 | Alembic `0001`→`0002` 成功；独立库 `flighthunter-live-test.db` |
| 三窗口（Web/Monitor/Sweep） | pwsh 启动；Sweep 全部 EXIT=0 |
| Web 控制台 | `http://127.0.0.1:8765/` 登录后页面与 API 正常 |
| monitor.py | 有 metrics；`--once` 输出告警（含冷却重扫 blocked） |

**结论：启动成功。** 后续问题均为业务质量/链路完整度，不是环境起不来。

---

## 2. 三条业务主线实际完成情况（诚实标注）

### 主线 A — 全球免费旅行抽奖：**partial**

| 指标 | 数值 | 说明 |
|---|---:|---|
| 真实候选 `campaign_rounds` | **8** | 来自 Sweepstakes Today 公开列表（非 Mock） |
| `verify_status=verified` | **0** | 未虚构官方核实 |
| `official_url` 已写入 | **1** | Lund Boats 候选官方页（仍为 candidate） |
| 聚合页证据 | **6** | `aggregator_page_snapshot` |
| 官方页证据 | **1** | `official_page_snapshot`（Lund） |
| 重复候选 | **0** | 幂等重扫未增长 |
| 自动报名 | **0** | 符合安全约束 |

**已跑通：** 公开聚合列表 → 候选入库 → 聚合页快照 →（部分）外链粗提官方候选 → 二阶段抓官方页快照 → UI/API 可见线索链接。  
**未完成：** Contest Girl 首页仅有导航（过滤后 0 条真实明细，需分类列表页）；多数“官方候选”仍是二级聚合站（contestbee 等），**不得**标 verified；规则/资格三态未在实机闭环验证。  
**样例候选（非中奖承诺）：** Ford Mustang GT 5.0、Lund Boats、TLC Giveaway、Camping World RV、Kia Canada EV5 等（标题级线索）。

### 主线 B — 行程福利与旅行卡包（日本优惠）：**partial**

| 指标 | 数值 | 说明 |
|---|---:|---|
| 真实 `benefit_offers` | **6** | Time Out Tokyo 等公开列表 |
| `date_certainty=confirmed` | **0** | 全部 unconfirmed，无伪领取 |
| 中文指南 `redemption_guides` | **3** | 含【待核实】；无假券码 |
| 领券/核销记录 | **0** | 未自动 claim |
| 卡包写入 | **0** | 无伪造券码入钱包 |

**已跑通：** 公开活动页 → BenefitOffer 候选 → `jp-benefits-scan` → 待核实中文指南。  
**未完成：** 领/约/用三窗证据、真实优惠券官方核验、卡包入册。

### 主线 C — 全球低价机票捡漏雷达：**partial**

| 指标 | 数值 | 说明 |
|---|---:|---|
| `fare_deal_signals` | **17** | 什么值得买等社区公开页 |
| 含金额信号 | **9** | 如 148/399/499/999 元级爆料 |
| `urgent_verified` | **0** | 无授权供应商报价 |
| 实时可买报价 | **无** | `quote_provider_enabled=false`（配置） |
| 报价供应商一致性 | N/A | 情报模式，无供应商 |

**已跑通：** 社区列表 → 信号入库（status=parsed / price_unconfirmed）→ 与攻略噪声分离（修复后）。  
**未完成：** 真实航司/API 实时报价、`urgent_verified`、订阅匹配命中。

---

## 3. 已修复缺陷（本轮实机暴露 → 开发分支修复）

| # | 问题 | 修复 | 提交要点 |
|---|---|---|---|
| 1 | 工具包/日志用 Windows PowerShell 5.1 → 中文日志乱码 | **强制 pwsh**；`1_start.ps1` 内 `Start-Process pwsh` | `AGENTS.md` §4 规则；工具包脚本 |
| 2 | CLI/TaskRun 漏报 `raffles_persisted`（显示 signals=0 却已入库） | CLI 表格 + TaskRun message 增加 `raffles=` | `app/cli.py` |
| 3 | 抽奖解析把导航/分类当候选（Contest Archives 等） | `parse_raffle_label` 黑名单 + 分类后缀过滤 | `html_fetcher.py` + 回归测试 |
| 4 | 机票纯攻略/怎么买 标题入库噪声 | `parse_deal_label` 噪声过滤；保留价格/促销门槛 | 同上 |
| 5 | 活动页表头列错位、主办方重复、无线索可点 | `campaigns.html` 五列对齐；`source_list_url` 可点 | `pages.py` / `api.py` / 模板 |
| 6 | 溯源只存聚合快照、不尝试官方链 | 粗提官方外链候选 → 二阶段 `official_page_snapshot`；不自动 verified | `provenance.py` |

**测试：** `pytest tests/unit` → **181 passed**；`ruff check` 相关文件通过。  
**未采纳/仍 partial：** Playwright 真外站提交、IMAP、实时票价供应商、手机推送、104 项全绿。

---

## 4. 重复扫描与数据质量

- 强制清除 `last_fetch_at` 后重扫 Contest Girl：`raffles=0`（无新增）→ **幂等通过**。  
- 冷却窗口内再 discover：`batch=blocked`（符合 `fetch_interval_hours`），monitor 记 `EXECUTION_PARTIAL_OR_BLOCKED` 为预期告警，不是崩溃。  
- `dup_rounds=0`；无 IntegrityError。  
- 无 `benefit_claims` / `entry_attempts` 自动提交。  
- 未验证条目均保持 `candidate` / `unconfirmed`。

---

## 5. Web 与数据库一致性

| 检查 | 结果 |
|---|---|
| `/api/v1/ops/status` | sources_fetched_24h=7，fare_deals=17 |
| `/api/v1/campaign-rounds` | 返回 `source_list_url`；多数 `official_url=null` |
| `/campaigns` 页面 | 含 Ford 标题；有「线索页」链接；5 列表头对齐 |
| `/api/v1/benefits` | unconfirmed 候选与 DB 一致 |
| `/api/v1/fare-deals` | price_unconfirmed 社区线索 |

---

## 6. 产物路径（均已脱敏；不含 Cookie/令牌/完整库）

| 文件 | 路径 |
|---|---|
| 本报告 | `docs/FIRST_LIVE_REPORT.md` 与 `data/live_tests/20261030_010245/FIRST_LIVE_REPORT.md` |
| 结构化结果 | `data/live_tests/20261030_010245/RESULTS.md` |
| 指标事件流 | `data/live_tests/20261030_010245/events.jsonl`（自 metrics 复制） |
| 监控告警 | `data/live_tests/20261030_010245/alerts.jsonl` |
| 执行日志 | `data/live_tests/20261030_010245/logs/`（sweep/setup/web） |
| 隔离源码快照 | `data/live_tests/20261030_010245/snapshot/` |

---

## 7. 总评

**首次真实运行成功启动并完成限量公开源抓取。**  
有效业务结果：**抽奖候选 8 + 官方页证据 1 + 聚合证据 6；日本福利候选 6 + 待核实指南 3；机票信号 17（含金额 9）。**  
系统在「不造假、不自动提交、不虚构 verified」约束下工作正常；三条主线均为 **partial**，下一步应做：Contest Girl/分类列表深挖、官方规则与资格三态、机票供应商接入、福利三窗证据。

**Git：** 修改均在 `develop`，未 force push `main`，未自动合并。
