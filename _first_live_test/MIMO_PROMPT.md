# 给 Xiaomi MiMo / Codex 的首次真实运行监控任务

你现在是 FlightHunter V1.0（R3）的「实机运行监控与故障定位工程师」，目标不是堆 pytest 数字，也不是每修一个小 bug 就导出一次审核 ZIP。当前审核基线 HEAD 为 `1d69efb11534de2e1d249689a55f51addec51c3e`。工作分支为 develop；不合并 main。首先实际确认 Git HEAD，发现不一致立即说明，不要擅自覆盖。

**环境隔离**：用户电脑是 Windows 11，仓库原始 `data/flighthunter.db`、`data/auth.json`、用户令牌、Cookies 与个人旅行资料均不可触碰/上传。首轮使用 `_first_live_test/1_start.ps1` 建立的 `data/live_tests/<timestamp>/snapshot/`，由 git archive HEAD 建立隔离快照和独立 SQLite。不要把隔离快照的数据写回用户正式数据库。不要试图索取真实 API Key / 凭据或上传整库。

**阶段 A：先核查可运行性**
1. 核对隔离 HEAD 与 SQLite 迁移版本，运行 doctor、三模块 dry-run、Web health/鉴权/页面。
2. 独立复现并修复：`app/alembic/env.py` 没有使用 CLI `--config` 指定的 DB URL（传入测试配置却迁移默认库）；修改后写跨两份 SQLite 的回归测试。`app/db/session.py::init_db` 不应对旧库字段不兼容静默 `pass`。
3. 修复 `app/web/routes/pages.py` 首页真实行程计数 `.where(not Trip.demo_only)` 恒为 0；修正 `app/web/templates/campaigns.html` 列头/列值错位，未核实聚合来源应显示可查看的独立线索链接、不可冒充官网。所有变更在单独工作树/工作分支进行，不能热修正在运行的隔离快照。

**阶段 B：小流量真实外网执行**
1. 只读抓取真正的公开网页：先 raffle，再 trip/Japan，再 fare；每模块初次最多 1 个列表源，限流、超时、robots 与站点条款严格执行。HTTP 403/429/robots/terms 禁止绕过；按 source 记录失败原因。不要自动填写、报名、领取、支付、下单或启动持续无人值守爬取。
2. 监控每个步骤：`run_id, commit, timestamp, module, source_id, site_host, fetch_policy, robots_decision, http_status, elapsed_ms, parsed_count, persisted_count, duplicate_count, evidence_kind, status, error_code, error_message_sanitized`，输出结构化 JSONL 供独立控制台/仪表盘观察。没有证据时所有资格、券码、实时报价保持未知。
3. 监控程序异常之外的**业务静默失败**：`HTTP 200 + parsed=0`、`parsed>0 + persisted=0`、`抓取记录增长而有效候选不增长`、`重复扫描导致数据库唯一错误/证据膨胀`、`外部源受阻却显示 completed`、`原始来源是聚合站却标 official`、`未确认优惠却显示可领/已领`、`含 2 人条件的机票只有社区爆料却显示确认可买`、`UI 与数据库/API 的条目/状态不一致`。
4. 抽奖必须真正完成「聚合线索→核查主办方真实域名→活动官方细则→规则/时间/参与资格→确认状态」链路。当前 provenance 只保存页面快照，不自动发现官网，且可能反复保存相同聚合证据；请对照业务目标修复而非仅增加字段。日本优惠必须保留领取期/使用期/活动期不同维度；Time Out 是线索不是已确认券。

**阶段 C：MiMo 快速反应**
1. 持续读取 `RESULTS.md`、`alerts.jsonl`、脱敏后的 `logs/sweep.log` 和代码调用栈，对每个异常标记 P0/P1/P2、影响模块、可复现条件、证据文件/时间戳、根因假说、下一步动作。
2. 遇 P0（误操作正式库、越权外发、错误官方核实、虚假已领取、重复真实提交、数据库不一致）立即停止相关测试流程并保留现场，不自动重试。对于站点拒绝、限流和资格未知，不允许通过降低安全门槛来凑「成功」。
3. 每个修复从稳定代码基线开分支/工作树，用最小业务回归测试 + 相同真实来源低频重跑确认。不得仅凭 Mock 或 pytest passed 宣称外网链路完成。修复可以批量 commit，首轮整体验收结束再统一形成报告/审核包。
4. 监控窗口应持续刷新：最近任务、每模块成功/阻断、真实候选数、确认的官方证据数、HTTP 失败分布、重复数、三态资格、未确认券数、机票报价状态、最新异常与重试建议。原始 Token/账户信息/券码/完整 HTML 不得发给模型或进入共享报告。

**最终交付**：输出 `FIRST_LIVE_REPORT.md`（真实访问的网站来源、步骤、HTTP 与 robots 判定、是否解析/落库/官方核实、用户可见展示、每项缺陷复现、优先级和修复状态）、机器可读 `events.jsonl`、脱敏的关键证据、已修复代码与测试记录。明确把「成功下载网页」「成功解析候选」「官方核实」「资格确定」「领取成功」「实时机票可购」六个里程碑分别标记。不要再为增加审核轮次而修小项。
