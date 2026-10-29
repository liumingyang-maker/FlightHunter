## 0. HEAD 当前状态（与历史章节分离）

- **最新测试（开发环境）**：`105 passed` · `ruff` 全绿  
- **鉴权**：已接入 Bearer/Cookie；未登录私人 API → 401  
- **最新提交**：见 Git `develop`；差分审核 ZIP 每轮必出（`AGENTS.md` §4）  
- 历史章节中的 “54 passed / 无鉴权” 仅作演进记录，**不代表当前 HEAD**

---

**仓库**：https://github.com/liumingyang-maker/FlightHunter  
**分支**：`develop`（默认）  
**基线日期**：2026-10-29  
**设计包**：FlightHunter_V1.0_R3（114 项功能需求 / 104 项验收用例）  
**审核目的**：验证是否按设计包真实实现，而非 Demo / Mock 冒充完成

---

## 1. 请你（审核方）如何使用本仓库

1. 阅读本文件全文，再按第 4 节矩阵抽查代码。
2. 本地可复现命令（Windows / Unix 均适用；Python **3.12**）：

```bash
uv sync --extra dev --python 3.12
uv run ruff check .
uv run pytest -q
uv run python -m app.cli doctor
uv run python -m app.cli seed --safe \
  --travel-plan fixtures/travel_plan.example.json \
  --fare-signal fixtures/fare_signal.example.json
uv run python -m app.cli discover --dry-run
uv run python -m app.cli web --host 127.0.0.1 --port 8765
```

3. **最近一次本地结果（HEAD 见 §0）**：
   - `pytest`：见 §0（当前 **105 passed**）
   - `ruff check`：All checks passed
   - 早期提交历史仅作演进参考

4. 请**重点验证**「是否用 Mock/空接口冒充 done」（见第 6 节反作弊清单）。

---

## 2. 产品一句话

面向个人的三引擎本地优先平台：

1. **全球免费旅行抽奖**（Campaign / Round / EntryAttempt）
2. **行程福利与旅行卡包**（Trip / BenefitOffer / Wallet）
3. **全球低价机票捡漏雷达**（FareWatch / Signal / Quote / Risk）

技术栈严格按设计包：Python 3.12 · uv · httpx · Pydantic v2 · SQLAlchemy 2 · Alembic · SQLite · FastAPI · Jinja2 · Playwright（依赖已引入）· pytest · ruff。

---

## 3. 架构地图（审核入口）

```
app/
  core/errors.py          # 统一错误码（与设计包 06 对齐）
  core/state.py           # 状态机；unknown 禁止自动重试
  config.py               # YAML 配置，与 04_config.example.yaml 同构
  models/                 # SQLAlchemy：campaign / trip / fare / shared
  schemas/                # Pydantic 输入输出契约
  db/seed.py              # 仅 demo fixture 种子
  services/
    trips/                # 行程创建、持续扫描订阅、重匹配
    benefits/             # 领券幂等、卡包、中文指南
    fare/                 # 信号导入、风险分层、匹配、成本、历史
    eligibility/          # 三态资格 + 逐条 rule_checks
    entry/                # 报名状态机 + 报名中心视图
    browser/prefill.py    # 预填守卫（不绕过 CAPTCHA/私网）
    discovery/            # 来源抓取 → RawCandidate
    verify/               # 官方页核实（证据不足绝不 verified）
    extract/              # 保守字段提取
    notify/               # 站内通知去重
    export/               # 行程 JSON/ICS（无券码）
  scheduler/jobs.py       # 可恢复扫描 + 幂等 TaskRun
  web/                    # FastAPI + Jinja2 页面 + /api/v1
  cli.py                  # doctor/seed/discover/web/...
tests/unit/               # 54 项单测/集成
docs/ADR/0001-project-bootstrap.md
```

**旧项目衔接**：未找到 `flight_raffle_starter`，全新建工程；见 ADR-0001。不继承任何「当前有效抽奖」假设。

---

## 4. 功能实现矩阵（设计包 ID → 状态）

状态定义：

- **done**：有真实逻辑 + 有测试或 CLI/API 可操作路径（非 TODO）
- **partial**：骨架/主路径已有，完整验收用例或真实站点覆盖仍缺
- **blocked**：依赖用户账号/API Key/平台条款，当前环境无法合法完成

### 4.1 抽奖引擎（DISC / VERIFY / RULE / ENTRY / TRACK / UI / OPS）

| ID 范围 | 状态 | 证据位置 | 说明 |
|---|---|---|---|
| DISC 来源注册/适配器 | partial | `models/shared.py` Source；`adapters/`；`db/session.py` ensure_default_sources；`services/discovery/` | 已有 httpx+RSS 适配器、robots 拒绝、RawCandidate 落库；多语言搜索 API 适配器未接付费源 |
| VERIFY 证据与核实 | partial | `services/verify/`、`services/extract/` | 状态机强制；证据不足 → needs_review；PDF/多语言条款完整解析未做完 |
| RULE 资格 | done（核心） | `services/eligibility/` + tests | 三态 + rule_checks；「未找到限制 ≠ 明确不限」 |
| ENTRY 报名助手 | partial | `services/entry/`、`services/browser/prefill.py`、`api /entries/*` | 幂等键、unknown 禁重试、预填计划已实现；Playwright 实机填表未接真实站点 |
| TRACK 进度/提醒 | partial | EntryAttempt/Receipt/WinningCheck 表；notify 服务 | 邮件只读中奖检测未启用（需用户授权） |
| UI 控制台 | partial | `web/` 页面 + API | 首页/行程/雷达/卡包/设置已通；活动详情证据页、完整筛选待加强 |

### 4.2 行程福利 TRIP-01～29

| ID | 状态 | 说明 |
|---|---|---|
| TRIP-01～03 行程 CRUD/分段 | done | `services/trips` + API + 测试；非法日期拒绝 |
| TRIP-04～05 来源包/多语言词 | partial | 默认社区源已种；国家来源包生成器未完整 |
| TRIP-06～07 权益类别/时间窗 | done（模型层） | BenefitOffer 四窗 + date_certainty 枚举强制 |
| TRIP-08 匹配 usable/maybe/not | done | `rematch_trip_benefits`；未公布 → maybe + BENEFIT_DATES_UNCONFIRMED |
| TRIP-09～10 资格/净节省 | partial | 资格三态复用；净节省在无预算时标未知 |
| TRIP-11 公开展示券 | done | PUBLIC_DISPLAY → wallet.saved，不造领取回执 |
| TRIP-12～14 合规领券/暂停/幂等 | done（策略层） | 付费拒绝、unknown 禁重领、需授权才 AUTO |
| TRIP-15 卡包 | done（基础） | WalletItem 状态；动态券不存截图逻辑在模型语义中 |
| TRIP-16 中文使用指南 | done（生成器） | `generate_guide`；未知字段显式 unknown_fields |
| TRIP-17～18 提醒/规则变化 | partial | BenefitReminder 模型 + 通知；变化重审流水线待接 |
| TRIP-19～20 UI/API | done（骨架） | `/trips` `/benefits` `/wallet` `/trip-benefit-matches` |
| TRIP-21～24 卡组织/变更重匹配/预约/导出 | partial | 导出 JSON/ICS done；预约跟踪未完整 |
| TRIP-25～29 持续监控 | done（调度核心） | TripScanSubscription 幂等、离线 recovery_pending、dry-run 调度 + 测试 |

### 4.3 机票雷达 FARE-01～24

| ID | 状态 | 说明 |
|---|---|---|
| FARE-01～03 愿望单 | done | FareWatchCreate 校验 + API + 人数 |
| FARE-04～06 来源/关键词 | partial | 手动导入 + 社区种子源；关键词簇扩展未全 |
| FARE-07～08 结构化信号/分类 | done | import_signal；子类型枚举；错价/漏油/甩尾分码 |
| FARE-09～11 报价适配器/比价/历史 | partial | record_quote + 历史样本 + 中位数（样本不足拒绝假历史）；真实 API Key 未配置 → blocked 于用户侧 |
| FARE-12 历史基准 | done | `historical_median_for_route` min_samples 默认 5 |
| FARE-13 两人完整成本 | done | `compute_cost_breakdown`；未知项不假精确上界 |
| FARE-14 风险引擎 | done | HIDDEN_CITY→high_risk；FUEL/ERROR→needs_review；opt-in |
| FARE-15 报价/爆料状态分离 | done | signal_status / quote_status / booking_status 三列分离 |
| FARE-16 补位三分类 | partial | 模型有 waitlist/seat_restock/award_space 子类型；官方候补确认流未接 |
| FARE-17 去重 | done | dedup_key UNIQUE |
| FARE-18 配额 | partial | 任务锁与预算配置存在；动态配额调度器待完善 |
| FARE-19 三级提醒 | done | urgent_verified 需真实 quote；无 quote 不得 verified + 测试 |
| FARE-20 Trip 联动 | done | trip_id 外键 + auto_attach 配置 |
| FARE-21～24 详情/UI/反垃圾/导出 | partial | API 齐；反垃圾规则仅基础 |

### 4.4 横切

| 项 | 状态 |
|---|---|
| 114 功能全部 **done** | **否** — 如上如实标注 partial/blocked |
| 104 验收用例全部自动化 | **否** — 当前 54 项自动化测试覆盖核心不变量；T01–T104 全文映射表见下轮迭代 |
| 真实站点 dry-run 抓取 | partial — dry-run 路径完整；真实抓取代码在，未在本报告宣称已覆盖全网源 |
| 不自动支付/出票/绕过 CAPTCHA | done（硬编码策略 + 测试） |
| 私密数据不进 Git | done（.gitignore；config 无真实密钥） |

---

## 5. 关键不变量（审核时请对照代码验证）

| # | 不变量 | 实现位置 |
|---|---|---|
| I1 | 资格三态；未知 ≠ 符合 | `eligibility/service.py` |
| I2 | 报名 `unknown` 禁止自动重试 | `core/state.py` ensure_no_unknown_submit_retry；entry service |
| I3 | 领券 `unknown` 禁止再次领取 | `benefits/service.py` |
| I4 | `saved ≠ claimed ≠ used` | WalletItem / Claim / Redemption 状态分离 |
| I5 | 社区爆料 ≠ 报价；无授权 quote 不得 `urgent_verified` | `fare/service.py` evaluate_alerts_for_match |
| I6 | 高风险（甩尾等）独立分栏，默认不进安心购 | risk_tier + accept_* opt-in |
| I7 | 成本未知不假精确 | compute_cost_breakdown |
| I8 | 历史样本不足不称「历史最低」 | historical_median min_samples |
| I9 | 行程日期用当地自然日；未公布活动 ≠ 已确认可用 | date_certainty + rematch |
| I10 | 预填不勾选营销、不绕过 CAPTCHA、拒绝私网 URL | browser/prefill.py + 测试 |
| I11 | 导出 ICS/JSON 无券码 | export/service.py + 测试 |
| I12 | dry-run 发现不访问外网 | discovery + CLI discover --dry-run |

---

## 6. 反作弊 / 反 Demo 清单（请审核方逐条核）

请确认代码中**没有**：

1. 大量 `pass` / `TODO` / `NotImplementedError` 却在矩阵标 done  
2. 用固定 Mock 返回值冒充「已抓取 100 个官方源」  
3. 把 HTTP 200 当作报名/领券成功  
4. 伪造「两人可买」「历史最低」「100% 有票」文案  
5. 在配置或 Git 中提交真实密码 / Cookie / 个人身份  
6. 自动购票、支付、改签工作流  

**当前自查**：矩阵中核心路径均有真实分支逻辑与测试；**未**宣称 114 项全部 done；真实外部 API/账号相关项标 blocked/partial。

---

## 7. 数据与隐私

- 默认 `demo_mode: true`  
- SQLite 本地 `./data/flighthunter.db`（已 gitignore）  
- 设计包示例日本 2027 行程 / 999 元机票均为 **fixture**，`demo_only=true`  
- 不上传私人行程到 CI；云端配置默认全关  

---

## 8. 已知缺口（诚实清单，供评分扣分参考）

1. Playwright 实机表单模板库与 DOM 指纹缓存未完成  
2. 邮箱只读中奖检测（TRACK-04）未实现（需用户 OAuth/IMAP 授权）  
3. 多语言搜索词生成器与付费 Search API 适配器未接  
4. 国家/城市优惠来源包（TRIP-04）自动化生成不完整  
5. 票价 API 适配器仅有接口与本地报价记录，无已配置供应商  
6. T01–T104 与测试文件的一一映射表尚未全部落盘为可执行用例  
7. 移动端 390px 逐页视觉验收未做截图归档  
8. Alembic 后续增量 revision 仅 initial  
9. API 仍无登录鉴权（仅默认 127.0.0.1；公开前必须加）  
10. 卡包 `encrypt_private_codes_and_receipts` 仅为配置位，完整加密存储未实现  

---

## 8b. GPT 独立审核（2026-10-29）响应与 P0 修复记录

审核结论：部分通过。已按报告修复下列问题，并附回归测试 `tests/unit/test_audit_p0_fixes.py`：

| 审核编号 | 问题 | 修复 | 回归测试 |
|---|---|---|---|
| P0-01 | 仅凭标题+购买词即可 verified | `verify/service.py`：须 **同源 + 购买证据 + 日期线索** 才 verified；**CAPTCHA 不否定 verified**，只降 automation | test_p001_* |
| P0-02 | 不可信报价可 urgent_verified | `_is_trusted_quote`：授权源、未过期、人数匹配；否则 urgent_unverified | test_p002_* |
| P0-03 | SQLite naive/aware 时间比较崩溃 | `ensure_aware_utc`/`dt_gt`；调度与资格统一 | test_p003_* |
| P0-04 | 无适配器任务标 completed | 无 fetch 时 `status=blocked`，不写 last_*_scan_at | test_p004_* |
| P1 URL | 私网/元数据地址可通过 | `app/core/url_safety.py` 全面拦截 + 重定向再校验 | test_p1_private_* |
| P1 日期 | 领取期误判为行程可用 | `_date_overlap` 使用期优先；五月领六月用 → 非 usable | test_p1_claim_month_* |
| P1 成本 | 可选未知费用仍给上界 | 任一未知字段 total_max=None | test_p1_optional_cost_* |

**本轮测试**：`72 passed` → **`82 passed`** · `ruff` 全绿  

### 第二轮核验：调用路径已接入（回应「是否只新增辅助文件」）

| 修复 | 实际调用位置 |
|---|---|
| P0-01 | `verify/service.py::complete_verify_from_html` 门槛重写 |
| P0-02 | `fare/service.py`：`match_watch_to_deals` + `evaluate_alerts_for_match` 均调用 `_is_trusted_quote` |
| P0-03 | `scheduler/jobs.py`、`eligibility/service.py` 使用 `ensure_aware_utc` / `dt_gt` |
| P0-04 | `run_subscription_scan` 无适配器 → `status="blocked"`，不写 `last_*_scan_at` |
| I10 | `prefill.py` 与 `html_fetcher.py` 均 `from app.core.url_safety import assert_public_http_url` |

复现：

```
git show --stat 805ed36
git grep -n "assert_public_http_url\|ensure_aware_utc\|_is_trusted_quote" -- app/
```

### CAPTCHA 与官方核实分离（按审核保留意见修订）

存在 CAPTCHA **不** 否定 `verified`；设置 `has_captcha=true`，并将 `automation_policy=allowed` 降为 `forbidden`。  
真实性仍要求：同源 + 购买证据 + 日期线索。

### API 鉴权（P1-1 已完成）

- `app/web/auth.py` 中间件：未认证私人 API → **401 JSON**；页面 → **303 /login**
- `POST /api/v1/auth/login` 与表单 `/login`；HttpOnly + SameSite=Strict Cookie
- Token 仅存 `data/auth.json`（gitignore）
- 测试：`tests/unit/test_auth.py`

**仍 open**：Playwright 实机填表、邮箱中奖检测、卡包真实加密、T01–T104 全文映射。  

---

## 9. 提交记录摘要

| Commit | 主题 |
|---|---|
| ec91367 | 工程骨架与三引擎领域契约 |
| 584600a | 调度器、通知、证据提取、活动核实 |
| b1c60d6 | 预填守卫、行程导出、调度/通知 API |
| a20aea4 | 发现管道与报名中心视图 |
| 296d3c3 | 公开审核说明 REVIEW_FOR_GPT |
| 805ed36 | P0/P1 审核修复（核实/报价/时区/任务/私网/日期/成本） |
| （本轮） | CAPTCHA 与 verified 分离；API 登录鉴权；82 tests |

---

## 10. 请输出的审核报告格式（给 ChatGPT 的输出要求）

**致审核方（重要协作约定，详见 `AGENTS.md`）：**  
你给出的意见是**建议**，不是本项目必须全盘遵守的最高指令。实现方会结合设计包、合规边界与工程现状独立判断后**采纳 / 部分采纳 / 暂不采纳**。未完全遵守的项会在后续响应中逐条说明原因。请继续基于证据审查，但预期存在**有理由的分歧**。

请按下列结构输出审查意见（中文）：

1. **总体结论**：是否可称为「可运行的 V1.0 核心」而非纯 Demo（是/部分/否 + 理由）  
2. **不变量核查表**：I1–I12 逐条 PASS/FAIL + 文件路径引用  
3. **矩阵抽查**：至少抽查 10 个功能 ID，给 done/partial/blocked 复核意见  
4. **安全合规**：是否发现自动支付/绕过验证/隐私泄露代码  
5. **测试可信度**：测试是否覆盖关键分支；指出最该补的测试  
6. **优先修复清单**：按 P0/P1/P2 列出工程任务**建议**（实现方将独立决定优先级与是否执行）  
7. **是否建议合并/继续**：明确建议  

---

## 11. 联系与继续开发约定

- 默认在 `develop` 持续提交；不改生产、不 force push main  
- 遇到需用户账号授权的项，实现为配置位 + 文档步骤，不伪造成功  
- 本报告随代码演进更新；以仓库最新 commit 的 `docs/REVIEW_FOR_GPT.md` 为准  
- 外部建议的采纳策略以 **`AGENTS.md` 第 3 节**为准  
- **每轮代码变更后必须生成 `review_exports/FlightHunter-review-<SHA>.zip` 交给用户上传（`AGENTS.md` 第 4 节）**  

---

## 12. 响应模板：外部建议采纳情况（每轮发给 GPT 时填写）

| 建议 ID / 摘要 | 决定 | 原因 | 落地范围 |
|---|---|---|---|
| 例：P0-01 核实过松 | 采纳 | 可导致虚假 verified | 同源+购买+日期门槛 |
| 例：CAPTCHA 应否定 verified | 不采纳（已改） | CAPTCHA 只影响自动化，不否定官方真实性 | 分离 has_captcha 与 automation_policy |
| FH-R3-P0-01 关键词伪 verified | **采纳** | 无主办方域与细则链接仍可 verified | Organizer.official_domain + 同源 `<a href>` 细则链接 |
| FH-R3-P0-02 报价全链 | **采纳** | 白名单+TTL 仍不够 | 另须 availability_confirmed、depart_date、币种 CNY、tax 已知 |
| FH-R3-P0-03 DNS SSRF | **采纳** | 字符串校验挡不住 DNS 指向内网 | resolve_and_assert_public_host；fetch 前解析；trust_env=False |
| FH-R3-P1-01 event/ redeem 冲突 | **采纳** | 购物券 6 月使用/5 月活动被 usable | shopping 类仅 redeem 可 confirmed |
| FH-R3-P1-03 robots 默认放行 | **采纳** | 403/异常应 fail-closed | 非 200 → 拒绝抓取 |
| FH-R3-P2-03 白名单 load_settings | **部分采纳** | 注入 settings 参数已支持 | 运行时默认仍 load_settings，CLI 可后续统一注入 |
| 立刻合 main / 实网无人值守 | **不采纳** | I5/I10 等仍 partial；设计包禁止 | 继续 develop |
| FH-R3-P1-05 Playwright 闭环 | **暂缓（如实 partial）** | 依赖本地模拟站与授权，非本轮 P0 能关 | 保持 partial/blocked，不标 done |

实现方对 GPT 建议保留最终取舍权；分歧必须书面说明，不得静默忽略，也不得无理由全盘照搬。

**审核用仓库 URL**：https://github.com/liumingyang-maker/FlightHunter  
