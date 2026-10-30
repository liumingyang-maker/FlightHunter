# FlightHunter 项目全貌说明（给 Codex / 独立审核）

**用途：** 告诉审核员这个仓库**到底是什么、文件干什么、从哪里开始读**，避免只盯单元测试或误删历史能力。  
**项目根：** `https://github.com/liumingyang-maker/FlightHunter`（本地：`C:\Users\97020\XiaomiMiMoProjects\FlightHunter`）  
**分支：** `develop`（审核以该分支最新为准；不合并 `main`）

---

## 1. 一句话定位

FlightHunter 是**个人本地优先**的国际旅行机会情报助手（FastAPI + SQLite + Worker），不是航司购票系统，也不是公开 SaaS。

三块业务（优先级）：

1. **P1 国际特价机票情报雷达**（最高）：多来源发现 → 解析 → 四频道分流 → Web/通知  
2. **P2 免费国际机票抽奖**：全球发现 + 官方证据 + 资格三态；优先中国内地出境相关  
3. **P3 Trip Benefits**：**仅确认真实行程后**搜目的地福利；无确认不正式扫  

**实时机票报价供应商已从 V1.0 强制目标取消**；情报 + 原始链接仍必须真实可用。  
**禁止**：自动购票/付款/未授权外站报名、绕过 robots/CAPTCHA。

---

## 2. 必须先读的文档（按顺序）

| 文件 | 作用 |
|---|---|
| `AGENTS.md` | 工程法则、安全硬约束、pwsh 规则 |
| `docs/PRODUCT_BASELINE_20261030.md` | **最新产品范围**（P1 优先、无强制报价 API） |
| `docs/FARE_FOUR_CHANNEL_DESIGN.md` | 四频道语义与路由 |
| `docs/REQUIREMENTS_MATRIX.md` | 需求完成诚实矩阵 |
| `docs/BUSINESS_VALUE_ACCEPTANCE.md` | 业务价值与四问 |
| `docs/ASIA_GLOBAL_FARE_INTEL_ACCEPTANCE.md` | 四频道+亚洲来源 |
| `docs/FARE_SOURCE_ACTIVATION_ACCEPTANCE.md` | FlyNext 等来源激活 |
| `docs/FARE_SOURCE_REGISTRY.md` | 来源注册表 |
| `docs/DAILY_RUNTIME_STATUS.md` / `DAILY_USAGE_ACCEPTANCE.md` | 日常运行 |
| `docs/CODEX_REMEDIATION_REPORT.md` | 对 Codex 12 缺陷的整改说明 |
| `docs/FARE_INTELLIGENCE_LIVE_ACCEPTANCE.md` · `FINAL_V1_LIVE_ACCEPTANCE.md` | 更早 V1/情报验收 |
| `docs/KOREA_GIVEAWAY_RECHECK.md` · `THIRD_LIVE_*` · `SECOND_LIVE_*` · `FIRST_LIVE_REPORT.md` | 韩国抽奖/行程/实机历史（部分数字已被后续纠正） |

文档冲突时：**以 `PRODUCT_BASELINE_20261030.md` + AGENTS.md 安全约束为准**，历史 LIVE 报告中的空频道/数字可能是当时快照，需对照代码与 `audit_evidence`。

---

## 3. 代码地图（审核从这里下手）

```
app/
  cli.py                 # doctor/seed/discover/worker/web/raffle-provenance/confirm-trip/source-health…
  config.py              # 配置；profiles 默认 CKG/TFU/CTU
  adapters/
    html_fetcher.py      # 公开 HTML/RSS 抓取+解析（机票/抽奖/行程标签）
    rss.py               # feedparser 条目
    base.py              # FetchResult / ParsedSignal
  core/
    url_safety.py        # SSRF/公网 URL 门槛
    state.py / errors.py # 状态与错误码
  db/session.py          # ensure_default_sources（fare/raffle/trip 种子）
  models/                # SQLAlchemy：fare_* campaign_* trip_* notification …
  services/
    airports/china.py    # 内地/港澳机场、国际航线判定
    fare/intel.py        # 情报过滤、城市匹配、去重、分类、质量统计
    fare/channels.py     # 四频道路由（my_origin/china_mainland/hk_mo/global_error）
    fare/service.py      # 信号导入、匹配、风险
    fare/quote_provider.py # 可选报价适配器（默认关）
    discovery/service.py # 来源抓取→物化→auto_verify 挂接
    raffle/              # 官方溯源、多轮、OCR 证据、auto_verify、中文指南
    trips/service.py     # 创建/更新/确认行程；**未确认不得正式扫**
    benefits/ wallet/ notify/ mail/ ops/
  web/                   # FastAPI + Jinja：fare/campaigns/trips/…
  scheduler/jobs.py      # 到期扫描；**再检查 trip.confirmed**
  alembic/versions/      # 0001…0004（含 trip.confirmed、source_health）
tests/unit/              # 200+ 单测（含 test_codex_remediation、channels、hk_activation）
_first_live_test/        # 隔离实机启动脚本（pwsh）
scripts/                 # 用户级 worker 启动项安装等
```

### P1 四频道关键文件
- 路由：`app/services/fare/channels.py`  
- 出发地：`app/services/fare/intel.py` · `app/services/airports/china.py`  
- 解析/价格：`app/adapters/html_fetcher.py`  
- UI：`app/web/templates/fare.html` · `GET /api/v1/fare/intel`  
- 来源健康：`app/services/ops/source_health.py` · `cli source-health`

### P2/P3 关键文件
- 抽奖物化/标签：`discovery/service.py` `materialize_raffle*`  
- 自动核验：`app/services/raffle/auto_verify.py`  
- 行程确认：`trips/service.py` `create_trip` / `confirm_trip` / `update_trip`  
- 调度：`scheduler/jobs.py` `claim_due_subscriptions`

---

## 4. 运行时与数据（本地，通常 **不在** Git）

| 路径 | 含义 |
|---|---|
| `data/daily_usage/config.yaml` + `fh_daily.db` | **日常隔离业务库**（Worker/Web 当前应指向此处） |
| `data/daily_usage/worker.lock` | 单实例锁 |
| `data/daily_usage/auth.json` | 该环境 Web 令牌（**勿提交**） |
| `data/live_tests/*/` | 历史实机快照 |
| `data/korea_recheck/` | 韩国活动截图/海报 |
| `review_exports/` | 审核包/上下文 |
| `backups/` | Git bundle + SQLite 备份 |

`.gitignore` 含 `data/`、`*.db`。审核时**不要**把正式 SQLite/`auth.json` 上传到模型上下文。

---

## 5. 默认机票来源（`ensure_default_sources`）

中国：什么值得买国际机票 / 每日推荐、北美票帝  
国际媒体/错价：OMAAT、View from the Wing、Secret Flying、Fly4Free、The Flight Deal、Travel-Dealz、Premium-Flights、Google News 若干  
港澳：FlyNext.hk、Flyday.hk（常 403）、Google News 香港  
亚洲：MainlyMiles、SingPromos  
抽奖：Sweepstakes Today、Contest Girl、VISITKOREA 美食栏目等  
行程：Time Out Tokyo、Japan Guide  

**注册 ≠ 成功产出**。看 `source-health` / `source_diagnostics`。

---

## 6. 审核时不要做的事

1. 不要只靠 pytest 数量宣布 V1.0 完成  
2. 不要把历史 LIVE 报告数字当成当前库实时状态  
3. 不要绕过 robots/登录墙  
4. 不要修改正式 `data/daily_usage` 或运行中的 Worker  
5. 不要自动修复后宣称 Codex 缺陷已关单——需复测  
6. 不要把「HTTP 200 / 0 解析」当业务成功  

---

## 7. 建议审核顺序

1. 读 §1–§2 文档建立需求基线  
2. 对照 §3 读 P1 四频道与 P2/P3 代码  
3. 复现 `CODEX_INDEPENDENT_AUDIT.md` 中 D-001~D-012；对照 `CODEX_REMEDIATION_REPORT.md` 是否已修  
4. 负例：上海→香港、香港航空上海、香港→大阪、HK$、20KG、全球错价空偏好、未确认行程编辑  
5. 输出 `CODEX_INDEPENDENT_AUDIT.md` / `CODEX_AUDIT_MATRIX.json`（PASS/PARTIAL/FAIL/BLOCKED/NOT_TESTED）

---

## 8. 仓库与版本

- GitHub：`https://github.com/liumingyang-maker/FlightHunter`  
- 本地 develop 在 push 后应与 origin/develop 一致  
- 整改相关：`15c123c`（代码）· `149da51`（整改报告）  
- 原 Codex 审计源：`603bb48`
