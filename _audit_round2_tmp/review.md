# FlightHunter：GPT-6 第二轮独立差分审核报告

- 审核时间：2026-10-29
- 源码来源：用户上传 `FlightHunter-review-a49fecfe.zip`；不依赖当前 GitHub 网络访问。
- 包内自报基准 SHA：`805ed36ba8a28abad72314a6dc3a1b35acf5e286`
- 包内自报 HEAD SHA：`a49fecfec08ccbd2359c3206c73695d340af614f`
- 审核范围：`source/` 全部实际跟踪源码（重点与 P0/P1 有关的调用路径），`reports/changes.diff`，`reports/pytest.txt`、`reports/ruff.txt`、`manifest.json`，完整阅读 `source/docs/REVIEW_FOR_GPT.md` §1–§11。
- 完整性边界：该包不含 `.git` 仓库、GitHub Actions 运行证明、实时网站凭据；HEAD SHA、基线 SHA、提交/推送事实由导出清单陈述，不构成独立远端验证。

## 1. 总体结论

**部分通过：可以称为“可运行的核心工程基础”，但不能称为可验收的完整 V1.0。继续在 develop 开发；暂不合并 main，暂不允许实网无人值守抓取/表单提交/对外开放私人 API。**

积极进展：P0-03（SQLite naive/aware 时间比较）和 P0-04（无抓取适配器却报告 completed）在代码路径与已有回归测试中得到针对性修复；CAPTCHA 和官方真实性状态已拆分；匿名私人 API 现在返回 401。但上轮 P0-01 与 P0-02 仍能被新边界测试复现，I9 与 I10 也仍不成立。

**切勿把 82 tests passed / Ruff green 推导为 114 功能完成或 104 验收通过。**

## 2. P0 复测（四项逐项关单）

| 项 | 判定 | 代码位置与实测证据 |
|---|---|---|
| P0-01 官方真实性 | **FAIL，未关闭** | `app/services/verify/service.py:56–98`、`app/services/extract/service.py:55–101`。使用 `https://example.org/campaign` 的模拟同源 HTML，其标题仅为“Example news index”，正文只有“订阅邮件无需购买”和 `2027-03-01`，仍得到 `verify_status=verified`。`source_url` 是传入字符串，购买/日期没有与抽奖规则语义绑定，非官方核验成功。 |
| P0-02 可信报价/紧急通知 | **FAIL，未关闭** | `app/services/fare/service.py:198–374,459–562,565–628`。虚构 `provider=totally_unregistered_provider`、`quote_expiry_utc=None`、`availability_confirmed=False`、报价 LAX→JFK 与信号 CKG→NRT 不一致、报价 ¥500 超过 ¥100 预算，完整业务链仍生成 `alert_level=urgent_verified`。`_is_trusted_quote` 只是拒绝有限的几个 provider 字符串，非白名单核验；通知未阻断日期、预算、航线等不匹配。 |
| P0-03 SQLite 时间比较 | **PASS（当前检查范围）** | `app/core/timeutils.py:17–50`、`app/scheduler/jobs.py:30–42`、`app/services/eligibility/service.py:125–139` 已调用 UTC 统一方法；`test_p003_sqlite_naive_datetime_compare` 在本地通过。尚不意味着所有时间处理/时区需求已覆盖。 |
| P0-04 无适配器成功状态 | **PASS（当前检查范围）** | `app/scheduler/jobs.py:99–131` 无 `fetch_fn` 时 `status=blocked`、`success=False`，不会更新 `last_benefit_scan_at` / `last_fare_scan_at`；对应本地测试通过。调度器仍缺真实长期抓取适配器接线。 |

**CAPTCHA 分离：PASS。** `verify/service.py:73–87` 中 `HUMAN_CHALLENGE` 仅设置 `has_captcha` 并将 `allowed` 下调为 `forbidden`；不参与 `verified` 布尔条件。`tests/unit/test_audit_p0_fixes.py:96–122` 两项测试本地通过。但“verified 判定”本身仍不够严格（见 P0-01）。

**匿名鉴权：PASS。** TestClient 请求 `GET /api/v1/profiles` 不带凭据返回 HTTP 401，已确认 `app/web/app.py:25–49` 注册 `AuthMiddleware`，`app/web/auth.py:117–144` 在私人 API 上拦截。不能由此推导会话安全完备。

## 3. I1–I12 不变量核查

| 编号 | 结果 | 代码证据及限制 |
|---|---|---|
| I1 未知资格不当作符合 | **PASS（核心三态）** | `app/services/eligibility/service.py:18–176`。多项缺失规则保持 `needs_review`；居住国/年龄实际规则数据仍不完整。 |
| I2 unknown 禁止自动重复报名 | **PASS（主操作路径）** | `app/services/entry/service.py:42–80,116–130`，`app/core/state.py:351–357`。但 `entry/service.py:164–180` 对非 `submitting` 调用 `finish_submit_unknown` 可直接篡改状态，属于额外 P1。 |
| I3 unknown 禁止再次领券 | **PASS（状态约束）** | `app/services/benefits/service.py:94–179,182–223`。真实领券执行器仍未实现。 |
| I4 saved、claimed、used 不混淆 | **PASS（模型/状态层）** | `app/core/state.py:229–245`，`app/services/benefits/service.py:263–309`。实际领取凭据不能仅按字符串视为已核实。 |
| I5 社区爆料不能冒充可信实时报价 | **FAIL** | `app/services/fare/service.py:459–562`，假供应商/未确认库存/错航线/超预算依旧 `urgent_verified`，已复现。 |
| I6 高风险甩尾票独立处理 | **PASS（规则分层）** | `app/services/fare/service.py:51–74,262–279,505–518`。来源全链路和 UI 仍未完整验收。 |
| I7 未知费用不给虚假上界 | **PASS（函数层）** | `app/services/fare/service.py:377–437`，任一可选必要费用未知时 `total_max=None`，相关测试通过。 |
| I8 历史样本不足不宣称最低价 | **PASS（最少样本约束）** | `app/services/fare/service.py:440–456`，少于5份返回 `(None,n)`；样本币种、仓位、日期/人数尚未规范化。 |
| I9 旅行日匹配正确 / 历史未公布不等于确认 | **FAIL** | `app/services/trips/service.py:284–324`，函数在匹配窗口前未检查 `date_certainty`；`historical_reference` + 5月使用日期被返回 `usable`。另一个测试：使用期6月但 event 期5月也返回 `usable`，需要按优惠类型定义优先级而非 `redeem/event` 任一即可。 |
| I10 URL/验证码/预填保护 | **FAIL（SSRF 边界）** | 预填营销字段/CAPTCHA 基本防护存在于 `app/services/browser/prefill.py:31–87`，但 `app/core/url_safety.py:44–92` 未阻止数字别名 `2130706433`、`0x7f000001`、`0177.0.0.1`、`127.1`（均能解析到 loopback）；`app/adapters/html_fetcher.py:59–95` 在 `follow_redirects=True` 请求后才检查重定向目标。用 `httpx.MockTransport` 离线验证：确实已经访问模拟 `127.0.0.1/admin` 才拒绝最终 URL。 |
| I11 导出 JSON/ICS 无券码 | **PASS（已实现字段）** | `app/services/export/service.py:13–114` 未包含券码字段。未来扩展时仍需回归。 |
| I12 dry-run 不访问外网 | **PASS（发现路径）** | `app/services/discovery/service.py:77–108`，dry-run 在创建适配器前返回；对应测试在当前环境因缺 `feedparser` 没有独立运行。静态路径通过。 |

**统计：9 PASS、3 FAIL（I5、I9、I10）。** PASS 只针对所述不变量范围，并非对应模块 `done`。

## 4. 设计功能 ID 抽查（至少10项）

| 功能 ID | 复核状态 | 说明 |
|---|---|---|
| DISC-03 | partial | RSS/HTTPX 适配器和候选入库存在，但暂无完整自动发现闭环；本环境的 RSS 测试受缺依赖影响。 |
| DISC-07 | partial / 安全阻断 | SSRF 数字地址、DNS 与重定向安全边界未修复；不宜暴露任意 URL 抓取。 |
| VERIFY-02 | partial / 缺陷严重 | 证据行存储有实现，但不能支持真实 `verified` 级别。 |
| VERIFY-03 | partial | 只识别“no purchase”和日期形式，无法确定是否属于活动条款、官方资格。 |
| RULE-02 | partial | 三态判断存在，居民国、年龄规则结构化不足；不得将核心三态 PASS 误解为完整 done。 |
| RULE-09 | partial | 每次/每日/家庭等周期控制未完成实网验收。 |
| ENTRY-01 | partial | `build_prefill_plan` 只输出字段计划，没有实际 Playwright 自动填写工作流。 |
| ENTRY-08 | partial | 幂等约束存在，`finish_submit_unknown` 可以被非法状态调用，完整提交后状态保护待完善。 |
| TRACK-04 | blocked / 未实现 | 中奖邮件只读检测未实现，需要用户授权；不能标 done。 |
| UI-08 | partial | API 匿名 401 已实现，但会话/退出/开放重定向有缺陷，不应宣称安全远程访问完成。 |
| TRIP-08 | partial / FAIL | 使用期与领取期初步分离，但未公布/历史日期仍可被当作确认 usable。 |
| TRIP-12 | partial | 领券策略守卫有逻辑，真实领取执行器尚未完成。 |
| TRIP-15 | partial | 卡包模型存在，私密券码的实际加密存储还没有实现。 |
| TRIP-16 | partial | 中文指南生成器存在，官方证据及使用条款无法保证完整。 |
| TRIP-25 | partial | 定时任务和订阅逻辑存在；无适配器时正确 blocked，但不等于已进行长期扫描。 |
| FARE-09 | partial | `record_quote` 可保存数据，不代表已连通合法票价供应商，也不能证明有座。 |
| FARE-12 | done（受限函数层） | `historical_median_for_route` 有最少样本控制；完整历史同口径比较需增强。 |
| FARE-13 | done（受限函数层） | 未知费用不给确定总价上界，已复测。 |
| FARE-14 | partial | 风险分类存在，尚无完整官方条款与来源校验。 |
| FARE-19 | partial / FAIL | 紧急提醒逻辑存在，但可由假报价触发，不能认定完成。 |

## 5. 安全与合规

- **未发现**自动支付、自动出票、验证码破解、绕过二步验证或未经授权群发社交内容的实装流程；不等于已全量安全审计。
- **未发现**上传包包含真实 `auth.json`、`.env` 或明显私人凭据；导出工具只能按文件名阻拦一部分敏感文件，无法保证 diff 与测试日志不会泄露已被提交的秘密。
- **安全缺陷 S1（P0）**：SSR F（服务端请求伪造）防护只看用户输入字符串，不做可靠目标解析/连接前判定；重定向先跟随后校验，已被离线模拟证明。
- **安全缺陷 S2（P1）**：`app/web/auth.py:86–102` 使用无时间戳、无服务端撤销的签名 Cookie；本地实测退出登录后重放旧 Cookie，`/api/v1/profiles` 返回 200。
- **安全缺陷 S3（P1）**：`app/web/routes/pages.py:32–58` 允许任意 `next`，本地实测登录成功返回 `303 Location: https://example.invalid/redirect`，构成开放重定向。
- **安全缺陷 S4（P1）**：`app/web/routes/auth.py:32–38` 未设置 `Secure`，也没有完善的远程 HTTPS 模式/CSRF 风险说明；本地 loopback 可接受，切勿直接对外开放。
- **配置隐患（P2）**：`auth.enabled=False` 可关闭鉴权；应禁止非 loopback 部署时关闭，或强制检查显式风险确认。

## 6. 测试可信度与优先补测

上传包 `reports/pytest.txt` 声称在 Windows Python 环境 **82 passed（退出码0，约7秒）**，`reports/ruff.txt` 显示 `All checks passed!（退出码0）`。我已检查日志与 `manifest.json` 一致，**但仅表示包内开发环境报告如此**。

本环境为 Linux + Python 3.13，`feedparser` 和 Ruff 不可用：

- 全量 pytest 收集报 `ModuleNotFoundError: No module named 'feedparser'`，不代表被测发现逻辑失败。
- 独立运行 `python -m pytest -q --ignore=tests/unit/test_discovery.py`：**79 passed**。
- 独立运行 `tests/unit/test_auth.py tests/unit/test_audit_p0_fixes.py`：**28 passed**。
- `python -m compileall -q app tests`：**通过**。
- 79 项执行子集覆盖率 `app` 全局约 **77%**。其中 `app/services/entry/service.py` **0%**、`discovery/service.py` **0%**、`adapters/html_fetcher.py` **0%**；覆盖率是执行子集的统计，不能作为整套 V1.0 的质量背书。
- 独立模拟边界结果：P0-01 虚假已核实、P0-02 虚假 urgent_verified、I9 历史优惠 usable、I10 私网数字别名/模拟 HTTP 重定向成功访问、会话重放和开放重定向均已复现。未向真实内网、航司、商家发起请求。

**必须优先新增的10项回归测试：**

1. **T-VERIFY-SEMANTIC**：普通新闻/订阅页即使包含购买关键词和日期，也不能转 `verified`。
2. **T-FARE-PROVIDER**：不存在于受信任供应商注册表的 provider、缺报价签名/来源凭据不能 `urgent_verified`。
3. **T-FARE-FRESHNESS**：未提供 TTL、实际过期、库存未确认均不能被当成近期可购买报价。
4. **T-FARE-MATCH**：报价/愿望单的出发地、目的地、日期、人数、币种、预算不一致，紧急已核实必须降级或拒绝。
5. **T-SSRF-DNS**：数字/十六进制/缩写 IPv4、IPv6 映射、DNS A/AAAA、解析变化和环境代理不能访问本地/内网/元数据地址。
6. **T-SSRF-REDIRECT**：模拟 302 跳转到 127.0.0.1，断言**没有发送**目标请求（不是发送完才报告拒绝）；robots 请求也覆盖。
7. **T-TRIP-CERTAINTY**：历史/未公布券即使字段含旅行期间日期也不得 `usable`；event 与 redemption 不同窗需按类别判断。
8. **T-AUTH-EXPIRY**：过期会话、退出后旧 Cookie 重放、服务端令牌轮换都不得再获授权。
9. **T-AUTH-REDIRECT-CSRF**：登录 `next` 必须是站内路径；Cookie/HTTPS/跨站有副作用请求有测试。
10. **T-ENTRY-STATES**：`confirmed`/`cancelled`/`rejected` 不得被 `finish_submit_unknown` 改写；未知提交后不得自动再发。

## 7. 依优先级排序的下一轮工程任务（12项）

### P0 — 先修，再接真实网页

1. **FH-AUDIT-P0-01｜重构 verified 判定**：必须用确凿的主办方授权域名和本轮活动对应条款/日期/参与资格证据；无可靠匹配保持 `needs_review`。`HTML + 来源 URL 字符串` 不等于官方证明。补新闻订阅页反例、历史日期反例、子域/重定向反例。
2. **FH-AUDIT-P0-02｜可信机票报价建立白名单及关联验证**：只允许启用的合法报价适配器/授权来源；绑定查询上下文、真实报价结果、时效 TTL、航线和行程日期、乘客人数和价格币种；缺少可购买证明时禁止 `urgent_verified`。
3. **FH-AUDIT-P0-03｜修正机票紧急通知**：检查 `OVER_BUDGET`、`PARTY_SIZE_MISMATCH`、日期未知或不匹配、报价与 watch 不同路由、费用未知等 reason codes，绝不可报“已核实适合购买”；补不可信及过预算的端到端本地测试。
4. **FH-AUDIT-P0-04｜完整修复 URL/SSRF**：连接前 DNS A/AAAA/IPv4 数字别名/IPv6 检查，逐跳手动重定向校验（禁止 `follow_redirects=True` 自动跳转），robots.txt 同策略；防 DNS rebinding，必要时锁定校验过的 IP；测试应断言没有内部请求发出。

### P1 — 安全和使用正确性

5. **FH-AUDIT-P1-01｜修复 trip 日期置信度**：`historical_reference`、`not_yet_announced`、`unconfirmed` 任何时段匹配只允许 `maybe_usable`/待核实；`event`、`redeem`、`booking`、`claim` 按优惠类别区别判断。
6. **FH-AUDIT-P1-02｜会话安全**：服务端最大有效期（`URLSafeTimedSerializer` + `max_age` 或存储会话 ID）、登出撤销、密钥轮换、Secure/HTTPS 模式；保留默认 localhost 安全使用。
7. **FH-AUDIT-P1-03｜站内重定向 + CSRF**：`next` 限站内相对路径，拒绝 `//` 和外部方案；补 cookie 登录后的有副作用 API 请求 Origin/CSRF 校验。
8. **FH-AUDIT-P1-04｜报名状态机收紧**：`finish_submit_unknown` 必须要求 `submitting` 或受控指定转换，不能对任何状态直接写 unknown；事件日志 from_status 真实记录。
9. **FH-AUDIT-P1-05｜必要能力闭环**：Playwright 模拟站预填、HTML 提交状态/回执真实核验、券码加密及中奖邮箱只读检测；用户授权与阻塞项继续标 `partial/blocked`，严禁假完成。

### P2 — 工程完整性与维护

10. **FH-AUDIT-P2-01｜测试/追踪**：逐项建立 T01–T104 需求映射；重点补发现与报名服务当前0覆盖的关键路径；CI 附真实依赖环境、日志和 commit SHA。
11. **FH-AUDIT-P2-02｜审核说明一致性**：`docs/REVIEW_FOR_GPT.md:28–31,193–204,222–253` 中 “54 passed”、”API 仍无鉴权“等旧信息与新修复相互矛盾，统一为 HEAD 当前状态并保留历史章节。
12. **FH-AUDIT-P2-03｜导出包隐私防泄漏**：对 diff/日志做敏感文本检查与显式人工确认，避免只靠敏感文件名过滤；继续禁止推送私人用户数据到 GitHub。

## 8. 合并/继续建议

- **继续 `develop`：YES**，保留现有架构和已通过修复，勿推倒重写。
- **本轮 PR 合并 `main`：NO**，至少 FH-AUDIT-P0-01～04 关闭并独立重测后才考虑。
- **真实网站无人值守自动报名/领券：NO**，Playwright、凭据、真实性及安全校验尚未满足要求。
- **公开暴露 LAN/WAN 端口：NO**，会话安全与 CSRF/HTTPS 尚需修复。
- **下一轮差分基准**：建议继续以本轮 `a49fecfec08ccbd2359c3206c73695d340af614f` 为比较起点；MiMo 每次打包应提供 HEAD SHA、base diff、pytest/ruff 原始日志，并附这份审核报告作为本轮输入。

### 防冒充完成的额外说明

发现的**明确“结果升级过度”**：`verify_status=verified` 和 `urgent_verified` 可以由不充分的证据产生，属于业务状态误报。真实抓取、Playwright、邮箱、加密、104项验收等代码仍然 `partial/blocked`，当前并无证据证明它们已经完成；不应把缺少实现的能力仅凭模型、配置开关、接口或 fixture 归类为 done。
