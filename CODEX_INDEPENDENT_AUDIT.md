# FlightHunter 独立审计与集中整改建议

审计日期：2026-10-30。GitHub `develop` 远端和本地 HEAD 在审计时均为 **`ac0c447fc33db1c011f1d443560f495f5ac4298e`**。GitHub 网页读取被工具限制，实际通过已配置 Git 远端的 `ls-remote` 与本地匹配提交读取；`git diff --stat 15c123c HEAD -- app tests` 为空，因此上轮对 `15c123c` 相同业务代码的隔离复验可作为补充证据，不能当作本轮重新操作私有环境。

## 结论与产品定位

这是一个**本地优先的个人旅行机会助手**，不是公共 SaaS 或自动购票系统。V1 不要求实时报价供应商，但要求发现真实情报、保留链接、准确区分已知/未知和证据。项目已有真实来源、四频道、抽奖、行程福利、鉴权、Worker 和测试基础；在这些已有能力之上修复，不建议重写。

| 问题 | 结论 | 理由 |
|---|---|---|
| 是否可作为安全可靠的个人每日工具？ | **NO** | 正式入口与 OCR 访问存在内网重定向风险；真实多目的地票价错配；行程设置存在停扫回归。开发者可在隔离条件下继续测试，但不能当成可靠结果。 |
| 满足完整 V1.0？ | **NO** | P1 数据语义、P2 证据与内地出境推荐、P3 生命周期，以及需求清单和真实运行证据尚未完整闭环。不是因为没有实时报价 API。 |
| 面向公众的技术/安全上线准备？ | **NO** | 当前是本地单用户产品，公网部署、访问隔离、完整安全验收未做；这不是法律结论，也不建议为本轮额外扩大公网产品范围。 |

## 独立证据与限制

- 本次独立重跑单元测试：**228 passed，1 warning，11.70 秒**；测试结果不是 104 项验收。用内存 SQLite、合成输入和 HTTP/通知替身验证边界，未对真实内网发包、未触发真实 toast、未提交任何外站表单。
- 本次按应用的抓取适配器和 robots 策略只读 FlyNext 首页：HTTP 200、解析 4 条，隔离库的港澳视图显示 3 条。HK Express 文章有台湾约 HK$800、大阪约 HK$1,500；视图却输出 HKG→KIX、HKD 800。原文：[FlyNext 活动](https://flynext.hk/blog/hk-express-13-anniversary-ultra-offer-2026)。这是报道估算，不代表当前可买。
- 上轮对相同代码做过 Edge 隔离浏览器测试：恶意标题、摘要未执行，危险协议链接被过滤；全球频道请求未附默认偏好机场。该测试使用模拟 API 数据，不代表正式数据库到页面的完整攻击链，也不是全站 XSS 验收。
- 不读取或使用 `data/` 私有数据库、`auth.json`、Cookies 或真实个人档案。各历史运行/来源报告是当时记录，不视为本次实时数据；72 小时连续、真实通知、断网恢复和线上部署未独立验证。审核覆盖了 `app/` 的相关关键路径及应用地图，**不是每个文件逐行安全审计**。

## 原 12 项整改的独立复验

| 原编号 | 结果 | 说明 |
|---|---|---|
| D-001 | PASS（原门槛） | 未确认编辑不再被调度；另有已确认行程停扫回归 N-007。 |
| D-002 | PASS（所测情报页输入） | 隔离浏览器注入样本未执行；完整攻击链/全站仍未测。 |
| D-003 | FAIL | 上海→香港仍可误命中 HKG 偏好；品牌假设也会误判。 |
| D-004 | PASS | 上轮浏览器观察全球频道请求无默认机场。 |
| D-005 | FAIL | 原最多減样例改善，立省 HK$800 仍会被视为票价；真实多路线错配。 |
| D-006 | PASS | 20KG 不再解析为 20000。 |
| D-007 | FAIL | 页面能区分发现与发布，但旅行日期可被错误写入 published_at；真实发布日期也有漏解析。 |
| D-008 | PARTIAL | 标题归一改善，改写转载仍可能分裂；保守部分采纳避免误合并是合理取舍。 |
| D-009 | FAIL | 短消息重复外送已改善；长消息标记被截断导致重复，失败也不能重试。 |
| D-010 | PASS（新候选） | 合成未知出发地候选不进核心；历史私库旧记录未复验。 |
| D-011 | PASS（原 HTTP200/空解析） | 模拟 HTTP200/0 parsed 返回 ok_zero；另有有解析但零新增被误报问题 N-011。 |
| D-012 | PASS（原真实样本） | 国泰×渣打样本目的地为未知，不再 HKG→HKG。 |

以上 **7 PASS / 4 FAIL / 1 PARTIAL** 仅针对原缺陷的验收范围，不代表相关模块或完整产品 PASS。

## 当前问题清单

严重性按对本地个人产品的风险与业务影响评估；模拟结果和代码审查分别标注，未把未完成的公网测试描述为已利用。缺陷含位置、证据、影响及可执行建议：

### N-001 · P1 · 入口探测和图片 OCR 的重定向可到达内网

- 位置：`app/services/raffle/auto_verify.py:99; app/services/raffle/evidence_extract.py:226; app/cli.py:727; app/services/discovery/service.py:110; app/services/fare/intel.py:700`
- 证据：httpx MockTransport 中 public.example 302→127.0.0.1，入口探测与 OCR 两条路径均跟随，入口返回 ok；无真实内网访问。初始 hostname 校验默认不解析 DNS，且 follow_redirects=True。
- 影响：受控外部页面或重定向可诱导服务访问本机或内网；其他直连路径需分别核查。
- 建议：统一安全 HTTP 客户端：每跳 URL/DNS/站点策略校验，禁止非公网，限制大小与跳转；防 DNS 重绑定要将校验结果与连接绑定并保留 TLS 主机验证，避免只在请求前解析一次。

### N-002 · P1 · 多个读取路径绕过统一 robots 安全策略

- 位置：`app/services/raffle/auto_verify.py:120; app/services/discovery/service.py:110; app/services/raffle/evidence_extract.py:230`
- 证据：入口 probe、AJAX 列表、OCR 图片直接使用 httpx，未调用 HttpxFetchAdapter 的 robots 路径；代码审查。
- 影响：来源主页面允许不等于其子路径、图片或重定向目标允许，可能违反项目自动化边界。
- 建议：所有自动抓取复用同一合规客户端；每站 403/429/CAPTCHA/robots 按状态停抓，不得绕过。

### N-003 · P1 · 目的地及航司品牌误识别为出发地

- 位置：`app/services/fare/intel.py:292; app/services/fare/channels.py:route_channels`
- 证据：隔离执行：上海→香港 机票促销→[PVG,HKG]，经 build_intel_view 在 HKG 偏好进入我的出发地主列表；Peach 大阪→首尔→[HKG]。
- 影响：误导偏好匹配或错归港澳。
- 建议：优先方向明确的地点和 IATA；目的地与航司名不作为出发证据。品牌只能作来源上下文弱提示，不满足明确匹配；未知归 unknown。

### N-004 · P1 · 多目的地价格与航线错误绑定

- 位置：`app/adapters/html_fetcher.py:457; app/services/fare/intel.py:380`
- 证据：2026-10-30 本次 FlyNext 首页只读 200，四信号隔离物化：HK Express 台湾 HK$800、大阪 HK$1500 的文章被视图输出为 HKG→KIX HKD 800。
- 影响：给消费者错误的大阪报价，不能认为是实时可买价格。
- 建议：用路线级候选或保留多目的地汇总，只有金额与目的地绑定证据充分才展示路线级价格；不明确则金额/目的地为 unknown 并保留原文。

### N-005 · P1 · 减免词绕过导致优惠额冒充票价

- 位置：`app/adapters/html_fetcher.py:482`
- 证据：香港大阪機票立省HK$800→reported_total=800 HKD；最多減样例返回 None。
- 影响：用户把折扣额误认成机票价。
- 建议：明确区分票价、减免、门槛、积分、行李及税费；未知语义不要写 reported_total，并覆盖简繁中英文变体。

### N-006 · P1 · 旅行日期可被写入发布日期

- 位置：`app/adapters/html_fetcher.py:215`
- 证据：合成列表「旅行日期 2027年2月3日」→published_at 2027-02-03；含 HK$1600 和明确發布 2026-10-29 的另一条 published_at=None。
- 影响：时间排序、过期判断会失真，旧文可能被伪装成近期发布。
- 建议：只解析有明确发布日期标签/RSS 字段的时间，使用来源时区；分别保存发现、发布、销售、旅行时间及证据，未知不回填。

### N-007 · P1 · 已确认行程在关闭编辑重扫后被停用

- 位置：`app/services/trips/service.py:103; app/services/trips/service.py:221`
- 证据：隔离内存：confirmed=true 且已有 enabled 订阅，auto_scan_on_trip_change=false 后编辑标签，订阅变 disabled，paused_reason=trip_not_confirmed；历史 disabled 订阅确认后仍不恢复。
- 影响：真实用户已确认行程可能停止福利监控。
- 建议：区分未确认与不触发重扫；确认动作幂等恢复符合政策的旧订阅；由调度器二次拦截未确认及 demo。

### N-008 · P1 · 社区促销被归为官方促销

- 位置：`app/services/fare/intel.py:447; app/web/templates/fare.html:130`
- 证据：合成 source_type=community、deal_types=[flash_sale]，classify_signal 返回 official_or_flash_promo；界面显示官方/限时促销。
- 影响：促销性质和来源权威被混淆，降低证据诚实度。
- 建议：来源可信度与促销类别分字段，社区转述标社区线索，仅直接官方证据才能标官方。

### N-009 · P2 · 抽奖资格缺一个关键档案仍返回 eligible

- 位置：`app/services/raffle/multi_round.py:580; app/cli.py:775`
- 证据：合成规则同时要求非韩国公民且不住韩国，purchase_required=false、age=30、nationality=CN、residence=None→eligible；反向缺 nationality 同样 eligible。该函数用于合成档案 CLI 路径。
- 影响：合成验证输出过度断言，可能误导审核；本次未证明真实用户资格 API 走此函数。
- 建议：每项规则拆开判断，任一必需档案缺失则 unknown；年龄阈值必须来自规则证据，不固定假定 18。

### N-010 · P2 · 失败外送不重试、长内容可重复外送

- 位置：`app/services/notify/delivery.py:67`
- 证据：替身送达：短内容成功重复调用只外送一次；4000 字正文截断 [delivery] 标记后外送两次；第一次 toast failed 后第二次被跳过。
- 影响：丢提醒或重复提醒；未触发真实桌面通知。
- 建议：独立持久化事件键、每渠道送达状态与重试次数；仅成功渠道幂等抑制，失败可限次退避。

### N-011 · P2 · 已解析但无新增被误报为零解析

- 位置：`app/services/discovery/service.py:768`
- 证据：隔离来源首次 parsed=1/persisted=1/status=ok；重复运行 parsed=1/persisted=0/status=ok_zero。
- 影响：正常去重的来源被误判为解析空，运营诊断不可靠。
- 建议：分开 fetch_ok、parsed_count、existing_count、new_count、valuable_count；仅 parsed_count=0 表示 zero_parse。

### N-012 · P2 · 非 demo 活动被标为真实

- 位置：`app/web/templates/campaigns.html:24; app/web/routes/pages.py:175`
- 证据：模板仅按 demo_only 显示 fixture 或真实；candidate、无官方证据的非 demo 数据同样显示真实。
- 影响：把线索存在与活动已核实混为一谈。
- 建议：数据来源与验证状态分别展示；candidate 标待核实，不以非 demo 推断真实。

### N-013 · P2 · 自动核验成功数被称为 verified

- 位置：`app/services/discovery/service.py:887; app/scheduler/jobs.py:269; app/services/raffle/auto_verify.py:410`
- 证据：代码以 auto_verify 返回 ok 数统计 verified/auto_verified，而返回 note 明示 not verified；未证明真实 round.verify_status 被改为 verified。
- 影响：监控数字容易被误读为官方核实或资格通过。
- 建议：使用 auto_extracted_count 等明确名称；verified 仅统计正式核实状态，展示核验失败和人工复核数。

### N-014 · P2 · 跨站转载无可靠事件级合并

- 位置：`app/services/fare/intel.py:88; app/services/discovery/service.py:251`
- 证据：上一轮相同代码隔离测试：两站同标题合并，第三站改写同一活动后仍为两个组；物化 key 包含来源 ID。
- 影响：重复展示且通知缺少统一事件依据。
- 建议：先提供保守候选合并和人工确认、保留全部原始来源及不合并歧义；避免仅凭相同航线价格强制全自动合并。

### N-015 · P2 · 正式 toast 调用 Windows PowerShell 5.1

- 位置：`app/services/notify/delivery.py:33`
- 证据：替身 subprocess 检测 argv[0]=powershell；项目 AGENTS 明确要求 pwsh。
- 影响：违反项目 Windows 执行规则，可能引入编码或行为差异。
- 建议：使用明确 pwsh.exe 路径及安全参数传递；测试保留中文、引号并禁止拼接可执行脚本。

### N-016 · P2 · 抽奖核心推荐没有正向识别路径

- 位置：`app/services/discovery/service.py:453; app/services/raffle/auto_verify.py:380; app/web/routes/pages.py:175`
- 证据：当前 materialize 将 core_recommend 固定为 false；代码搜索未发现将已核实中国出境设置为 true 的路径；页面只展示简单活动列表。
- 影响：修复误推荐的同时，尚不能产出有证据的中国出境核心推荐。
- 建议：增加独立证据驱动的适用性三态和核心推荐筛选，未知继续待核实；无官方资料不得硬推。

### N-017 · P2 · 建表不等于已有数据库结构迁移

- 位置：`app/db/session.py:45; app/web/app.py:29; app/alembic/versions`
- 证据：Web 启动 init_db 使用 metadata.create_all，旧 official_url 情况只 pass；升级需独立 Alembic 命令。
- 影响：旧库启动可能缺新增字段或与当前模型不一致；本次未访问或迁移私有 DB。
- 建议：启动前检查迁移版本并给出清晰阻断/升级指导；先对隔离副本做备份、升级与回滚演练，正式库操作须用户授权。

### N-018 · P2 · UI 缺少完整情报筛选和反馈闭环

- 位置：`app/web/templates/fare.html; app/web/routes/api.py:339`
- 证据：产品基线要求目的地、类别、出行时间、过期过滤；现页面有出发地和过期控件，情报 API 不提供完整对应过滤；页面主要提供收藏。
- 影响：用户难以快速缩小到可用的个人行程，反馈能力与实际界面不一致。
- 建议：先建立结构化且可缺失的字段，再补目的地、类别、时间和反馈控件；未知项不能被误作已匹配。

## 建议一次集中实施的整改包

以下是**同一轮的完整工作范围**，包内顺序仅表示依赖和优先级；不需要每修一项就发来验收。保持现有技术栈、来源与安全边界；不要自动重置 72 小时观测，不要操作用户正式库。对于迁移、通知、来源等风险改动，先使用隔离库和模拟传输验证。每个包的验收条件应和真实证据一起交付。

### B1 · P1 · 统一外部访问和本地安全边界

覆盖：N-001, N-002, N-015。

实施：梳理 HTML/RSS、入口、OCR、AJAX、链接质量检查及浏览器子资源，统一允许的请求策略；每个重定向及 DNS 均执行公网检查，禁止访问本机和私网；连接层防重绑定并保留 TLS 验证；遵守 robots、限流和响应大小。Windows toast 使用 pwsh，参数与脚本分离。

验收：MockTransport 验证初始私网、公开跳私网、私网 DNS、重绑定、跨域 robots、403/429、过大响应全部拒绝；公网静态安全样本可访问；不访问真实内网。

### B2 · P1 · 统一机票语义与可信显示

覆盖：N-003, N-004, N-005, N-006, N-008。

实施：把来源角色、实际出发地、目的地、航司、价格类型、币种、发布/发现/旅行/销售时间分离并保留证据；对多目的地价格只展示被证据绑定的路线与金额；不确定值保留 unknown；杜绝品牌自动等于出发地。

验收：上海→香港、香港航空上海、Peach 大阪→首尔、真实 HK Express 多线路、立省 HK$800、20KG、旅行日期与发布日期、未知时间等全部通过；真实 FlyNext 样本前后对照，报道价仍标非实时。

### B3 · P1 · 四频道与消费者筛选闭环

覆盖：N-003, N-018。

实施：频道先按统一候选集与明确地域分流；全球不默认偏好过滤；全国不并入港澳；我的出发地只接受明确机场，未知折叠。补目的地、类别、时间范围、反馈与来源链接，保持小屏可用。

验收：同一 signal 可多频道但事件通知唯一；端到端 API 与浏览器测各频道、全国/HKG/MFM、偏好变更、未知及过期过滤；误命中率和漏报率基于标注样本公开统计。

### B4 · P1 · P3 行程状态机与恢复

覆盖：N-007。

实施：定义创建、确认、编辑、暂停、取消、完成、恢复的统一状态转换；任意正式执行入口复核 confirmed、demo、archived、completed；关闭改期自动重扫不应禁用已有订阅；旧脏订阅只在隔离副本核查后设计恢复。

验收：未确认、demo、confirmed、编辑设置开关、历史 disabled 订阅、取消/结束、重启均有端到端测试；未确认永不正式扫描，确认后可正确启用；不改动正式库。

### B5 · P1 · P2 官方证据与中国出境

覆盖：N-009, N-012, N-013, N-016。

实施：把候选、官方核实、免费、报名期、适用内地出境、真实用户资格、入口、回执拆开表达；每项保留来源和不确定性；只根据官方证据正向识别核心推荐。统计和页面均禁止把非 demo 或自动提取当 verified。

验收：国籍/居住缺一分别 unknown，完整冲突 ineligible，无官方规则/出发地 unknown；模拟已证实内地出境方可核心推荐；汽车/现金/国内航段排除；不真实报名。

### B6 · P2 · 来源、通知和事件去重

覆盖：N-010, N-011, N-014。

实施：来源健康分别记录 fetch、parse、已存在、新增、有效；通知采用事件+渠道的持久状态，成功去重、失败退避；跨站保守候选合并，保留全部 URL，提供可拆分与人工复核。

验收：已解析零新增不等于零解析；同一事件多源不重复通知，长正文不丢送达状态；失败可重试且成功不重复；相似不同活动不得误合并。

### B7 · P2 · 数据库与日常运行可靠性

覆盖：N-017。

实施：在隔离库验证迁移版本、备份恢复、旧 schema、单实例、断网恢复及故障状态；保留原 72h 观察起点，持续积累；不因验收重启用户 Worker。

验收：新库、旧库副本迁移与恢复演练可复现；失败不破坏数据；Web/Worker 同库单实例；72h 使用实际连续证据而非墙钟推断。

### B8 · P1 · 统一验收、交付和后续审计

覆盖：P1-CHANNELS, P2-HONESTY, P3-GATE, RUNTIME, V1-104。

实施：一轮完整实现后按需求 ID、负例、来源、界面、安全和运行证据统一出报告；明确 verified/unknown/blocked，附真实日志与可重现的隔离命令，不用 mock、200、测试数冒充真实业务。

验收：104 项逐项有证据或诚实标未测；真实网络受限标 BLOCKED；未修或部分采纳意见有原因；仅最后统一交 Codex 复验，不逐项往返。

## 本轮工程取舍

1. 保留 FastAPI + SQLite + Worker 和既有抽奖/OCR/行程能力，不为修复数据质量而整体重写。
2. 不把实时报价 API、额外来源数量或付费模型作为 V1 关门条件；对不允许访问或网络阻断的来源如实标 BLOCKED。
3. 跨源合并先保守执行并可追溯；无法确定同一事件时保留两条和来源，不为压低重复数误合并。
4. 不要求这轮完成公网 SaaS、渗透测试或全面 CSP；但本地运行也要修复已经复现的外部访问与私网重定向边界。
5. 修改需要数据库 schema 时，先准备可审阅的迁移、回滚及隔离副本验证；未经用户授权不碰私库，不重置运行观察。
6. 本次输出的是审计意见和批量验收标准，不代表要求机械接受每条方案。对重要取舍，在下一轮报告逐条说明采纳、部分采纳或不采纳及证据。

## 本次执行记录

- git status --short --branch; git rev-parse HEAD; git ls-remote origin refs/heads/develop
- git diff --stat 15c123c HEAD -- app tests
- PowerShell 7: PYTHONPATH=<project>; PYTHONDONTWRITEBYTECODE=1; .venv/Scripts/python.exe -B -m pytest tests/unit -q -p no:cacheprovider → 228 passed, 1 warning in 11.70s
- python -B stdin: SQLite :memory: cases, synthetic price/date/origin and eligibility probes, mocked delivery, HTTP MockTransport redirect, 200 parse/repeat accounting
- python -B stdin: robots-aware HttpxFetchAdapter read-only FlyNext homepage and in-memory fare materialization
- Prior turn on 15c123c identical app code: Playwright Edge isolated HTML with mocked API XSS/global-channel request; confirmed-trip lifecycle; no real toast or submissions

结构化需求、18 个缺陷和集中整改包详见同目录 `CODEX_AUDIT_MATRIX.json`。本次没有修改业务源码、没有推送，也没有自动修复；两份审计文件以未跟踪文件形式写入项目根目录。
