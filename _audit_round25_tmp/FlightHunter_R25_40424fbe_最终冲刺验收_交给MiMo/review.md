# FlightHunter V1.0｜主业务冲刺独立验收（R25）

**审核对象**：用户上传的 `FlightHunter-review-40424fbe.zip`（`develop`，HEAD `40424fbe6c1cfb28898adb72100d6339837a9789`，BASE `f7bd865fae93baa3a9c80ad6a50dc76969f68dd0`）。这是上传的 Git 快照，不等于我已直接验证 GitHub 远端 HEAD。

**审核方法**：完整阅读 `source/docs/REVIEW_FOR_GPT.md`、`FINAL_REPORT.md`、`REQUIREMENTS_MATRIX.md` 与冲刺差异；检查调用路径、默认配置、测试和代码；在无外网、无正式账号的隔离 SQLite 中运行负例和 166 项现有测试。**无法独立验证用户本机的 Chromium 实机操作和20+条在线来源数据**。

## 1. 总体结论

**部分通过：可称为「有真实业务逻辑的可运行 V1.0 核心工程」，尚不能称为三大目标全部验收完成或具备全面无人值守能力。**

正向证据：CLI doctor 成功；pytest 原有166项全部通过；Ruff Windows 运行日志 exit 0；调度、消息、票价情报、行程匹配、模拟报名、回执、Web/API 等有非空实现。此次冲刺增量实际集中于 `app/services/ops/status.py`、`app/services/mail/eml_scan.py`、`app/web/routes/api.py`、`app/adapters/html_fetcher.py`、报告与5个测试新增（详见 `reports/changed_files.txt`），既有大模块来自过去提交，不能都算作本次新开发。

**重要事实**：
- `FINAL_REPORT.md:6` 中 HEAD 仍写为基准 `f7bd865...`，且第7行保留 `{{ZIP_PATH}}`。应以审核包 `manifest.json` 的 `40424fbe...` 为版本依据；当前最终报告未按实际 HEAD 定稿。
- 文档称公开列表实抓 20+ FareDealSignal、Windows Chromium `confirmed`，但 ZIP **没有**独立的真实抓取日志/原始页面样本、Chromium 运行输出、脱敏 SQLite 查询记录或界面截图。属“开发端报告，待复核”，不可算审查方实测通过。
- `REQUIREMENTS_MATRIX.md` 是按 MON/SRC/GIV/TRP/FAR/INT 等能力的概要矩阵，**不是**114项原功能 ID 和104项验收的逐条结果与证据映射。文档承认有大量 partial/blocked，这一点诚实。

## 2. 独立执行结果与限制

| 项目 | 结论 | 证据 |
|---|---|---|
| 原始 pytest | 收集失败，缺失 `feedparser`，不是项目测试断言失败 | `evidence/pytest_raw.log` |
| 隔离执行已有测试 | **166 passed**，临时 `feedparser` 导入替身；不验证真实 RSS/Atom 解析 | `evidence/pytest_stub.log` |
| 开发端 pytest | `166 passed`, exit 0 | 审核包 `reports/pytest.txt` |
| 开发端 Ruff | exit 0，All checks passed；审查环境无 Ruff 可执行文件，未独立运行 | 审核包 `reports/ruff.txt` |
| CLI doctor | exit 0，数据库可写、Demo 模式、AI 未启用、票价适配器未配置 | `evidence/doctor.log` |
| 在线真实抓取与20+信号 | 未独立复核；审核包缺外网原始证据，且本审查环境无外网 | `FINAL_REPORT.md` 声明 |
| Windows Chromium 实机 | 未独立复核；审核包缺运行日志/回执快照 | `FINAL_REPORT.md` 声明 |
| 离线业务反例 | **3项实质缺口重现** | `evidence/probes.log`, `evidence/trip_probe.log` |

注意：离线测试替身只替代缺失模块的导入，相关 RSS 测试内部 monkeypatch 其 parse；真实 RSS 网络与解析实现未获验证。未对真实外部网站发起请求、支付或报名。

## 3. 业务功能推进：三个关键验收缺口

### MAIN-01：全球抽奖发现没有结构化业务闭环（核心缺口）

**离线已复现**：创建一个合法的 `Source(module='raffle')`，用纯本地 FakeAdapter 返回免费机票抽奖 HTML。`run_discovery(... module='raffle', dry_run=False)` 生成 `RawCandidate=1`，却 **`CampaignRound=0`**。见 `evidence/independent_probes.py` 与 `evidence/probes.log`。

根因是 `app/services/discovery/service.py` 的 `fetch_source` 在 `effective_module='raffle'` 时走通用/机票解析，后续 `materialize_*` 只为 `fare` 和 `trip` 建业务实体（约 `fetch_source:317–363`），无抽奖 round + evidence + qualification 的自动物化路径。`run_discovery` 后处理也只调 fare 和 trip（约 `run_discovery:422–455`）。所以「能抓网页」不可等同于「能自动报名真实新抽奖」。

**建议作为下一整项大业务功能**：从合规公开的真实官方来源进入候选 → 抽奖活动/轮次结构化 → 原文证据（截止、国籍/居住地、免费门槛、限制）→ 资格三态 → 待报名中心。自动提交仍遵守各站规则、授权和防重门槛；不得依赖虚假 Demo 成功。

### MAIN-02：行程福利监控默认没有目的地来源（核心缺口）

**离线已复现**：使用默认种子来源，新建非 demo 日本行程，自动生成 JP 的福利与机票监控订阅；默认来源仅3个 `fare` 社区源，没有 `trip` 福利源，实际 `benefit_discovery` 任务为 **`blocked`**。见 `evidence/trip_default_probe.py` 与 `evidence/trip_probe.log`。票价来源在本审查离线环境网络失败，不代表其线上不可用。

**建议下一整项大业务功能**：国家/城市官方来源包 + 合规公开页面/RSS监控 + 优惠发布日期/领券期/预约期/旅行使用期四窗分别理解；先作为待核实候选，取得可信官方规则再成为可领取/可用；卡包维持 saved ≠ claimed ≠ used。需要第三方授权的券保留人工领取步骤，不伪造领取成功。

### MAIN-03：真实运行的长期效果与证据（验收缺口）

当前已有 `worker`、`scan-due`、Windows 计划任务脚本、Toast 尝试和演示浏览器流程；但审核包没有：至少一次可复核的计划任务持续运行/重启恢复记录、真实抓取数据的匿名化原始证据链、实际提醒可见证据或 Chromium E2E 脱敏日志。默认 worker 只有使用 `--execute` 才访问网络；计划任务脚本由登录事件触发，并非证明24小时可靠。`app/cli.py:305–361`、`scripts/install_worker_task.ps1`。

**建议以一个可复现的整体验收场景取代不断补小测试**：本机 Windows 启动 + 恢复任务 + 一次公开来源抓取产生可溯源候选/业务记录 + 中国出发机票情报与日本行程福利按资格/日期匹配 + 站内或外送通知的实际送达状态 + 本地模拟报名 confirmed/回执持久化；同时给出失败路径和 24h 任务日志，不要求真实外站无授权自动提交。

## 4. 新增运维 API 的实质误报（随监控模块修正）

`app/services/ops/status.py:42–45,71–74` 把 `TaskRun.finished_at` 的最大值，只按 `dry_run=False` 过滤，命名为 `last_successful_execute_scan_utc`。**没有过滤 `status='completed'` 或确实成功的真实抓取**。隔离 SQLite 里仅创建一条 `failed` 任务，API 仍返回了“上次成功扫描”时间。见 `evidence/independent_probes.py`。

建议：将最近尝试时间、最近成功抓取时间分成两个字段，并给用户展示失败/blocked 的上次时间及原因。此问题不必单独停工修，但在系统对用户宣称“监控正常”前必须消除误报。

## 5. I1–I12 不变量核查（核心实现与真实环境分开）

| 不变量 | 代码/离线结论 | 依据与边界 |
|---|---|---|
| I1 资格三态 | PASS（代码） | `eligibility/service.py`; 真实多语言规则覆盖不全 |
| I2 unknown 不自动重试 | PASS（代码） | `core/state.py:351+`、`entry/service.py`、`entry/browser_pipeline.py` |
| I3 领券 unknown 防重领 | PASS（代码） | `benefits/service.py:182–222`；真实领券未验 |
| I4 saved/claimed/used 分离 | PASS（数据模型） | `benefits/service.py`, WalletItem；动态券真实凭据未验 |
| I5 爆料不等于可靠报价 | PASS（代码门槛） | `fare/service.py:498–550,578–630`；报价供应商未配置 |
| I6 高风险票独立 | PASS（代码） | `discovery/service.py:_risk_tier_for_subtypes`, `fare/service.py` |
| I7 未知费用不假精确 | PASS（代码） | `fare/service.py:391–449` |
| I8 历史样本不足不称最低 | PASS（代码） | `fare/service.py:454+` |
| I9 行程日期和未知适用性 | PASS（代码主路径）/真实待验 | `trips/service.py:_applicable_windows`, `rematch_trip_benefits` |
| I10 URL/自动操作安全 | **LIMITED** | `browser/playwright_exec.py:122–153` 已禁止真实外站自动提交；公开抓取 `html_fetcher.py:59–146` 的 DNS 预检与实际 HTTP 连接仍非同一绑定，存在 DNS 重绑定/TOCTOU 风险，启用不可信来源无人值守采集前需隔离/绑定连接目标 |
| I11 导出不带私密码 | PASS（代码/测试） | `export/service.py`; 不代表任何未来备份都安全 |
| I12 dry-run 不联网 | PASS（主路径） | `discovery/service.py:fetch_source` 与 CLI 设计；隔离测试覆盖 |

这里 PASS 是代码层或测试夹具范围的判断，不代表该业务引擎完整 done。

## 6. 抽查功能 ID（真实验收口径，超过10项）

| ID | 复核状态 | 说明 |
|---|---|---|
| DISC-03 | partial | HTML/RSS适配器存在；真实 RSS 缺独立验收、官方搜索能力不足 |
| DISC-06 | partial | 多类查询词的配置已有；动态多语言搜索未闭环 |
| VERIFY-02 | partial | 有证据模型、核实规则；自动抓取抽奖轮次未物化 |
| RULE-02 | done（核心逻辑） | 资格三态有实现，未证实不推断为符合 |
| ENTRY-01 | done（本地模拟）/partial（外站） | Playwright 本地模拟闭环有开发端声称，源代码支持；审查 ZIP 未附实机证明；真实站安全边界保留人工 |
| TRACK-04 | partial / blocked | IMAP适配器及新 `.eml` 候选扫描存在；没有账号实机验证，非真实中奖确认 |
| UI-08 | done（基础） | 鉴权及报名、通知页面存在，未验证外网/移动端部署 |
| TRIP-04 | partial | 官方国家城市福利来源包不足，默认0个 trip 来源 |
| TRIP-08 | done（核心逻辑） | 行程日期/城市匹配实现，未覆盖真实来源多样性 |
| TRIP-12 | partial | 领券策略与状态机有；真实合规领券未跑通 |
| TRIP-15 | done（加密读写核心）/partial（生产备份） | 钱包DPAPI/AES-GCM已有；备份恢复未验 |
| TRIP-25 | partial | 创建行程自动注册扫描；默认来源不足、24h持久运行待验 |
| FARE-09 | partial / blocked | 票价供应商接口存在，未提供真实授权的两人含税可买报价 |
| FARE-19 | done（信号提醒逻辑）/partial（真实送达） | 站内记录可生成；手机/Windows真送达没有独立证据 |
| OPS（运维状态） | partial | `/ops/status`已加，但最近成功时间有可复现误报 |

注意：本文件并未假装完成114项逐条验收，原始需求与104条用例仍需最终一次性对照并出具可点击证据链接。

## 7. 安全与合规核查

- 未发现本轮新增自动支付、自动购票、验证码绕过或绕过站点规则的实现；外站自动提交仍硬关闭（`playwright_exec.py:143–153`）。
- 本次上传快照未发现明显的真实 API Key 或私人邮箱密码；但没有 Git 历史全文，不能保证历史提交从未包含密钥。
- `app/core/url_safety.py` 的域名 DNS 预解析不保证实际 HTTP 客户端复用同一已审核 IP；对不可信来源自动抓取前必须补网络级限制或连接绑定，不能仅凭域名校验认为 SSRF 已根除。
- 新 `GET /api/v1/mail/eml-scan?dir=...` 支持认证用户选择任意本地目录并产生通知（`api.py:80–96`）。对于本地单用户尚属受控能力，若扩展为远程访问，须限定本地授权文件夹、改成显式动作接口并设置大小、数量限制；低于上面三项主要业务缺口的优先级。

## 8. 测试可信度与完成口径

- 本轮真正的新增测试 `tests/unit/test_main_sprint.py` 主要覆盖本地 `.eml` 关键词、ops返回结构、内存构造的日本优惠匹配和 wallet 保存、导入的机票信号与提醒、页面HTTP 200；**没有证明真实互联网抓取、海外优惠国家来源、浏览器实机、邮件服务器读取或24h运行**。
- `source/docs/FINAL_REPORT.md` 声称实机效果，但缺审计证据附件；建议以后将命令、退出码、去标识化输出、时间与版本号、SQLite查询结果、通知送达日志打包。不需暴露真实券码、邮箱或个人身份。
- 不将项目声明的 `partial`/`blocked` 升级为 `done`；也不把一次 FakeAdapter 测试等同真实官方活动抓取。

## 9. 风险和建议（不把建议误作对 MiMo 的命令）

### 上线安全门槛（启用前必须证明）
1. 不可信外链无人值守采集前，连接级拒绝私网/DNS重绑定；外站自动提交继续关闭，直到站点规则、授权和防重测试可验证。
2. 外部通知/领券/报名必须用可验证回执区分 accepted、unknown、claimed、delivered；不能用 HTTP 200 或日志打印充当成功。

### 下一次开发应该做的三个完整交付成果（优先于零散修复）
1. **抽奖引擎真实发现闭环**：一个合法公开官方抽奖来源，生成带证据的 CampaignRound，资格判断与报名中心联通；缺规则时停在 needs_review。
2. **行程福利真实来源闭环**：默认/可配置的日本官方福利来源，2027日本行程的真实或明确未公布状态，含时间窗、城市、中文使用指南和卡包；没有真实券时不能造 claimed。
3. **持续运行证据闭环**：实际 Windows worker、扫描入库、提醒、恢复的去敏感日志，与 Chromium 模拟站独立演示证据；票价报价没有API时明确维持 signal-only 模式。

### 普通技术债（随相应模块推进即可）
- `ops/status`上次成功时间误报；`FINAL_REPORT.md` SHA与占位符；完整114/104映射；HTML统一UTF-8损失部分非UTF8网站；邮件 GET接口设计等。

## 10. 是否建议继续/合并

- **继续开发 develop：建议。** 现有工程已具备大量可复用的业务代码和测试，勿推倒重来。
- **是否可进入本地受控试用：可以**，限只读公开来源/信号情报、手工核验优惠、模拟站报名及人工决定真实提交，不宣称实时可买或中奖确认。
- **是否建议合并 main 并称完整 V1.0：暂不建议。** 三个核心闭环及真实运行证据尚未达到最初目标。

**协作原则**：这是一份独立审核报告，不是 MiMo 必须逐项照办的任务清单。请 MiMo 基于项目事实独立判断取舍；安全门槛隔离，普通问题并入相关大功能；完成一整批真实能力再交付下一次审核包。
