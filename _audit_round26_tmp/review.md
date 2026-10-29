# FlightHunter 第26轮独立增量审核：e0279b36

**源码来源：** 用户上传 `FlightHunter-review-e0279b36.zip` 内 `source/`；基准 `40424fbe6c1cfb28898adb72100d6339837a9789`，目标 `e0279b366e53bb5516fea02274a8b5894386569e`。离线审核，不独立保证远端分支 SHA 或第三方页面当前内容。

## 1. 总体结论

**部分通过；继续推进 develop，不建议现在宣布完整 V1.0 已验收。**

本轮是扎实的“候选线索进入业务数据库”进展：`parse_raffle` → `materialize_raffle_candidates` → `Campaign/CampaignRound(candidate)` 的调用链实际存在；同 URL + 标题的重复扫描可以去重。默认来源加入 JP 行程来源与两个抽奖聚合站，`last_successful_execute_scan` 排除了失败 TaskRun。

但本轮**不能等同于可报名机票抽奖闭环**：抽奖列表只匹配关键词、未识别奖品是否旅行，自动生成的主办方为聚合站，官网及细则尚未溯源。日本行程来源大多是旅游内容列表，不是经核实可领取的优惠。CLI/运维还有零来源扫描被记成功的情况。

## 2. I1–I12 不变量（本轮增量与现有回归范围）

下表“PASS”表示**本轮无证据显示回归，静态代码/现有回归支持该核心约束**，并不替代未来的真实第三方网站实机验收。

| 编号 | 复核结论 | 证据与说明 |
|---|---|---|
| I1 资格三态 | PASS（现有核心） | `app/services/eligibility/service.py`：未知不能推断符合 |
| I2 报名 unknown 禁自动重试 | PASS（现有核心） | `app/core/state.py`, `app/services/entry/`；真实外站自动提交仍关闭 |
| I3 领券 unknown 禁重领 | PASS（现有核心） | `app/services/benefits/service.py` |
| I4 saved/claimed/used 区分 | PASS（模型/状态核心） | `app/models/trip.py`、benefits 服务；真券凭据端到端仍 partial |
| I5 爆料不等于可买报价 | PASS（当前回归范围） | `app/services/fare/service.py`，无授权真实可买价仍 blocked |
| I6 高风险机票独立处理 | PASS（现有核心） | `app/services/fare/service.py` |
| I7 未知成本不伪造上界 | PASS（现有核心） | `app/services/fare/service.py` |
| I8 历史样本不足不冒充历史低价 | PASS（现有核心） | `historical_median_for_route`；样本不足不计算可靠基准 |
| I9 未公布日期不视为旅行可用 | PASS（核心逻辑） | `app/services/trips/service.py`，仍待真实日本优惠源验证 |
| I10 外部网址预填与抓取安全 | **受限／上线门槛未全满足** | `app/adapters/html_fetcher.py:83–108` 先 DNS 检查再由 httpx 独立连接，DNS 重绑定/TOCTOU 缺少连接 IP 绑定；已有域名与重定向检查是积极防护 |
| I11 导出不泄露券码 | PASS（现有核心） | `app/services/export/service.py` |
| I12 dry-run 不联网 | PASS（现有核心） | `app/services/discovery/service.py:362–367` |

## 3. 功能 ID 抽查（包含已实现、部分与受限）

| ID/范围 | 复核状态 | 本轮与总体证据 |
|---|---|---|
| DISC-03 来源抓取适配器 | partial | HTML 抓取存在、代码可执行；真实 RSS 解析未在独立环境验证 |
| DISC-04 来源追踪/来源注册 | partial | `db/session.py:79–185` 新增7个默认源（其中2个JP、2个raffle）；不等于动态全球覆盖 |
| VERIFY-02 官方核实/证据 | partial | 候选为 `candidate`；自动发现候选主办方 `official_domain=None`，未完成聚合站到实际主办方溯源 |
| RULE-02 资格三态 | done（核心）/partial（完整规则覆盖） | 三态代码与单测存在；尚未自动抓取全部官方资格文本 |
| ENTRY-01 自动报名助手 | partial | 本地模拟 Chromium 开发端曾报告闭环；外站自动化禁用，当前包无新实机证据 |
| TRACK-04 邮件中奖识别 | partial/blocked | .eml 支持，IMAP 实机授权未验证 |
| TRIP-04 国家/城市优惠来源 | partial | `db/session.py:117–139` 新增 Time Out Tokyo、Japan Guide；只代表来源存在，不代表真实券已匹配 |
| TRIP-08 日期匹配 | done（规则核心）/partial（真实场景） | 规则与测试现存，2027真实活动不得虚构日期 |
| TRIP-16 中文指南 | done（生成器）/partial（外部证据） | 使用说明生成基础存在，仍缺真实商家条款长期跟踪 |
| TRIP-25～29 持续监控 | partial | worker/订阅/扫描具备入口，24h、真实通知送达仍待证据 |
| FARE-09 实时报价/库存 | blocked | 授权报价源未接，不能声称“可买、两张有座” |
| FARE-19 提醒 | partial | 情报匹配与提醒存在，但手机送达与实时报价受限 |
| UI 活动列表 | partial | `app/web/templates/campaigns.html:15` 将非 Demo 标为“真实”，应与“官方已核实”直观区分 |

## 4. 本轮关键发现：业务主线验收缺口（非逐个修复命令）

### R26-F01｜P1：普通抽奖被归为“机票抽奖”
- **位置**：`app/adapters/html_fetcher.py:344–368` / `app/services/discovery/service.py:267–274`。
- **复现**：离线 HTML 包含“厨房搅拌机 contest giveaway”“iPhone giveaway contest”“飞日本往返机票 giveaway”。运行真实解析 + SQLAlchemy 物化后，3条均写入 `Campaign.category='flight_giveaway'`，且状态为 `candidate`。详见 `repro_r26.log`。
- **影响**：候选数与产品的“免费机票抽奖”有效数量混淆；不应把聚合站的普通奖品数用于计算机票发现效果。
- **建议随抽奖发现主线合并解决**：先按奖品分类（机票／旅行套餐／酒店／其他／未知），未知不要默认标机票；保留低置信度原始线索。

### R26-F02｜P1：聚合网站被写作主办方；`official_url` 未经官网证明
- **位置**：`app/services/discovery/service.py:252–284`。
- **复现**：3条均 `organizer_name='Contest Girl 列表'`，`official_domain=None`，`official_url` 指向聚合链接。`verify/service.py:59–71` 要求真实主办方 `official_domain`，因此现有数据无法凭该占位直接走完自动核实。
- **影响**：`CampaignRound` 名称与来源准确性不足，后续用户无法可靠判断参赛资格和官网真实性；界面 `campaigns.html:15` 的“真实”目前只代表非 Fixture，容易误解为已证实。
- **建议**：在同一条抽奖完整闭环中明确 `source_page_url` / `entry_url` / `official_rules_url` / 实际主办方；必须先证实官方出处再 `verified`，不建议凭聚合域名直接升级。

### R26-F03｜P1（业务价值）：新增日本来源是线索种子，不是优惠券闭环
- **位置**：`app/db/session.py:117–139`、`app/adapters/html_fetcher.py:307–341`、`app/services/discovery/service.py:181–224`。
- **事实**：已新增两个 JP 来源；含 `free/event/festival` 等关键词的链接可被写成 `BenefitOffer(candidate, date_certainty=unconfirmed)`。该模块不读取真正的商家券码，也未从来源列表提取领取开始日和可用期。
- **注意**：`japan-guide.com` 是旅游指南，不是日本官方旅游机构；`kind='official_page'` 不准确，会影响来源可信度展示。
- **建议**：把能提供有效活动条款、日期、支付资格与官方领取入口的合规来源纳入默认 pack；对无法验证的普通旅游文章只作为发现线索，不把它当已可使用优惠。

### R26-F04｜P2：空来源批次仍可能显示 `completed` 并影响成功扫描统计
- **位置**：`app/cli.py:175–190` 与 `app/services/ops/status.py:42–46`。
- **复现**：真实调用 `run_discovery(module='raffle', after_fetch=False)`，当没有活动来源时返回 `[]`；CLI 的状态分支默认 `completed`，无 `results` 时不转 `blocked`。其 `TaskRun(status='completed', dry_run=False)` 会被运维接口记作“上次成功扫描”，即使0页被抓。
- **建议**：统一定义“调度结束”“成功获取至少1个外部页面”“产生有效候选”3个不同指标，随监控完整业务验收一起修正。

### R26-F05｜P2：新测试使用 Fake.parse，未覆盖新 parser
- **位置**：`tests/unit/test_r25_mainline.py:30–71`。
- **事实**：`Fake` 仅有 `parse()` 而无 `parse_raffle()`，实际跑入的是 `fetch_source` 的 fallback 分支 `adapter.parse`。真实 `HttpxFetchAdapter.parse_raffle()` 的分类与 URL 语义不在该测试覆盖内。
- **建议**：为网页 parser 添加包含真实页面结构特征的离线 fixture 及反例，测试奖品归类、主办方溯源和重复抓取，不要单纯增长测试条数。

### R26-F06｜上线门槛（继承旧风险）：不可信域名抓取需要网络连接级隔离
- **位置**：`app/adapters/html_fetcher.py:83–108` 与 `app/core/url_safety.py:109–150`。
- **事实**：解析地址前检测公网 A/AAAA，并逐跳校验重定向；但 httpx 仍自行建立连接，DNS 解析结果未用于绑定连接地址，理论上有 DNS rebinding/TOCTOU 窗口。
- **建议**：启用无人值守抓取陌生聚合网站前将网络策略落实到连接级或隔离出口；不要求为了这个遗留风险停止离线/受控开发。

### R26-F07｜P2：本轮“真实抓取数量”证据不在 ZIP 中
- **事实**：开发方报告 Contest Girl 23条 candidate、Japan Guide 可抓；ZIP 提供源码、增量 diff、pytest/ruff 日志，但没有对应 HTTP 响应摘要、脱敏候选列表或同一时刻 SQLite 导出，也没有 Chromium 新实机证据。
- **建议**：下次最终验收仅增加一份脱敏 `source_scan_evidence.json`：来源地址、HTTP状态、抓取时间、提取条数、入库状态、有效机票抽奖条数、未核实条数、失败原因。无需上传私人 Cookie/密码。

## 5. 安全合规

本轮增量未发现新引入自动购买、支付、绕过 CAPTCHA 或虚假 `verified` 的代码；新抽奖记录始终创建为 `candidate`，属于正确保护。未作完整历史密钥泄露审计，未观察到本轮新增明文秘钥。`official_url` 与奖品分类仍须官方证据约束。I10 的连接绑定问题仍为无人值守外链抓取上线门槛。

## 6. 测试可信度

- 开发端日志 `reports/pytest.txt`：**169 passed**；`reports/ruff.txt`：`exit 0`，`All checks passed!`。
- 本地独立运行：**169 passed**；环境缺少 `feedparser`，使用**仅用于模块导入的临时替身**，RSS 的真正读取/解析**未**得到独立验证。`ruff` 模块在此容器中不可用，因此只核对开发端 Ruff 日志。
- 新增3项测试核查：默认来源存在、Fake 抽奖候选入库、失败状态不记成功；但仍缺真实解析的反例、源到官网的证据链、真实抓取证据、0来源运行统计、真实 RSS/Atom 样本与权限限制。

## 7. 建议继续/合并

**建议继续 develop，暂不建议合并 main 或宣称完整 V1.0 正式完成。** 此次完成了“线索从网页落到抽奖候选”的重要一步，接下来应该用一个较大的功能集成把“奖品分类—官网溯源—资格判断”和“日本真实福利检索—可用时间匹配—提醒”一起做通。

**没有必要为 R26-F04/F05/F07 单独开下一轮小修 Bug。** 同时保留实现方自主权：建议的优先级与实现方式均可有理有据地调整，但不能将 `candidate`、`partial` 或 Mock 演示当作 `verified`/done。
