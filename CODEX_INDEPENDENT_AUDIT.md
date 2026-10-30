# FlightHunter B1–B8 独立复验

审计日期：2026-10-30。GitHub `develop` 远端及本地 HEAD 在核对时均为 `32544e4779bf0ee4afea16e755a5d1ae939f79bc`。该报告覆盖用户声明的集中整改，不代表对所有源码、104 项需求或公网安全做了全量测试。

## 结论

**B1、B2、B3、B5、B6、B7 未通过；B4、B8 部分通过。** 这不否定本轮改善：原未确认扫描门槛、部分出发地、立省与 20KG 负例、缺档案资格、全球频道、真实 FlyNext 错价样本均有改进。但仍能复现安全、数据准确性和业务闭环缺陷，不应按整包关单。

| 决策问题 | YES / NO | 依据 |
|---|---|---|
| 作为安全可靠的个人日常工具？ | **NO** | 安全抓取在拒绝内网重定向前可先访问目标 robots；实际业务仍可能串价、误推荐和重复提醒。 |
| 满足完整 V1.0？ | **NO** | 四频道过滤、抽奖核心推荐、来源状态和通知等尚未闭环；104 项、真实长跑和私库未验收。实时票价 API 非必要条件。 |
| 中国大陆公网发布技术安全准备？ | **NO** | 尚未完成公网部署安全验收，项目目前为本地优先；此项不是法律意见。 |

## 复验范围和证据

- 独立 `pytest tests/unit -q -p no:cacheprovider`：**248 passed，11 warnings，17.62 秒**。其中多条是 PowerShell 子进程 readerthread 的 GBK `UnicodeDecodeError`，不能省略警告。测试数量不等于 104 项完成。
- 所有网络安全和通知反例使用 `httpx.MockTransport`、内存 SQLite 与替身通知；模拟出现的 `127.0.0.1` 是拦截的请求记录，**没有访问真实内网**。模拟进程重启通过清空进程内状态，不等于真实桌面 toast 已测试。
- 本次使用遵守项目 robots 的抓取适配器只读 FlyNext 首页：HTTP 200，解析 4 条；隔离业务链港澳显示 3 条。此前错误的 HK Express 大阪 HKD 800 已变为价格未知，属于有证据的改善；其他合成多目的地标题仍会串价。
- 临时 SQLite 验证旧版本检查，不触碰正式数据库。未独立运行仓库迁移脚本或对真实旧库做迁移/回滚；未读私有数据库、授权凭据或 Worker 状态。72h、真实 toast、104 项全量与公网测试均为 NOT_TESTED。

## 八包复验结果

| 包 | 状态 | 主要证据 |
|---|---|---|
| B1 安全 HTTP 和 pwsh | FAIL | MockTransport: public.example → 127.0.0.1，在拒绝最终 URL 前请求了 127.0.0.1:9911/robots.txt；robots 403 时仍请求目标并返回 200；max_bytes=100 的模拟流读取 400 字节后才拒绝。两层验证未阻断 robots 先行请求；DNS 未绑定连接；外网重定向及策略有风险。 |
| B2 航线、金额和时间 | FAIL | 真实 FlyNext 4 条；HK Express HKG→KIX 价格已为 None；合成 香港出发 台湾 HK$800 · 大阪 HK$1500→HKG/KIX/800 HKD；大阪 MOP$1500→HKD 1500；无明确标签的 2025年1月2日被解析为发布日期。真实样本改善，但多目的地合成反例和币种/日期仍失败。 |
| B3 四频道筛选与反馈 | FAIL | 真实输出 signal_status=bookmarked，feedback=bookmarked 筛选 0；香港→上海 HKG/PVG 被国内过滤；目的地香港可因香港航空标题误匹配 KIX。新增控件不能等于筛选闭环；出行时间与发布/发现时间不同。 |
| B4 确认与行程状态 | PARTIAL | 内存 SQLite 未确认编辑无到期订阅；旧 trip_not_confirmed 订阅确认后恢复；已确认编辑且关闭重扫后仍启用；auto_attach_fare_watch_to_new_trip=False，确认后 fare_monitor 仍启用。原问题改善，配置边界尚有回归。 |
| B5 抽奖资格与证据 | FAIL | 合成官方候选「中国内地国内航班免费机票抽奖」和「不包括中国大陆出发的国际免费机票抽奖」均 core_recommend=true；缺国籍或居住时 synthetic eligibility=unknown。资格负例通过；官方来源及关键词不等于官方证明内地出境适用。 |
| B6 来源与通知 | FAIL | 相同通知发送后清空进程状态再发送→两次替身 toast；失败连续调用 5 次→5 次替身 toast，超过 3 次限制；来源第二次 parsed=1 返回 ok_existing，但 Source.last_result=ok_zero。不触发真实 toast；跨站改写合并本轮未重新验证。 |
| B7 迁移检查与隔离演练 | FAIL | 临时隔离 SQLite alembic_version=0001_initial；head=0004_source_health，check 报 ok=true、ensure action=ok；rg 检索实际 app 中 ensure_migrations_or_warn 无调用，Web 使用 init_db。只测试版本检查，不触碰私库；未独立重跑迁移脚本。 |
| B8 测试与统一验收 | PARTIAL | pytest tests/unit: 248 passed, 11 warnings in 17.62s；多个新增测试用 inspect/hasattr 或断言结果集合，未执行完整业务链。本轮抽样和隔离测试不等同 104 项验收；完整 72h、真实 toast/私库 NOT_TESTED。 |

## 已确认的问题与修复方向

下面的 P1/P2 是按现有本地产品风险评估；每项均可复现或标明测试范围，不代表在真实目标上已发生攻击。

### R-001 · P1 · 重定向目标验证之前先抓取 robots

位置：`app/core/safe_http.py:72`。

复现：MockTransport 从 https://public.example/start 返回 Location=http://127.0.0.1:9911/private；调用记录出现 http://127.0.0.1:9911/robots.txt，随后才报 unsafe_redirect。

影响：非公网 URL 在最终拦截前已收到请求；本次没有访问真实内网。

建议：每次跳转先验证 scheme、host、DNS，再访问该目标 robots/正文；robots 请求自身也使用同一安全连接策略。

### R-002 · P1 · robots 403/429 或异常时放行目标

位置：`app/core/safe_http.py:182`。

复现：MockTransport 返回 robots 403，目标仍被请求并返回 ok=true。

影响：违背项目遇到 403/429 及未知策略需停止的边界。

建议：robots 403/429/异常 fail closed；404 等状态按明确项目策略分类；不对站点拒绝进行绕过。

### R-003 · P2 · 响应上限在完整读取后才检查

位置：`app/core/safe_http.py:87`。

复现：max_bytes=100，模拟无 Content-Length 的 4×100 字节流；客户端先消费 400 字节，再返回 response_too_large。

影响：大响应可耗尽内存，robots 读取也未流式限量。

建议：使用流式响应按块限制解压后大小和耗时，robots 同样限量；预检仅为补充。

### R-004 · P1 · 多路线金额仍会跨目的地绑定

位置：`app/adapters/html_fetcher.py:424; app/services/fare/intel.py:538`。

复现：合成 香港出发 台湾 HK$800 · 大阪 HK$1500 機票優惠，隔离物化视图得到 HKG→KIX 800 HKD。

影响：把台湾票价误导为大阪价。

建议：结构化一条价格绑定一个已证实的目的地；有歧义返回多路线无单价或 unknown；全链路断言最终视图。

### R-005 · P2 · 澳门币种被解析成港币

位置：`app/adapters/html_fetcher.py:424`。

复现：大阪 MOP$1500 機票優惠→reported_total=1500 currency=HKD。

影响：错误币种影响价格判断。

建议：金额解析携带真实币种，MOP→MOP、HK$→HKD、¥ 按明确语境或保留未知。

### R-006 · P1 · 发布日期提取仍使用无标签日期

位置：`app/adapters/html_fetcher.py:382`。

复现：机票活动 2025年1月2日 机票优惠→published_at=2025-01-02；更新日期也写 published_at；真实 FlyNext Peach 明示 2026-10-29 但字段 None。

影响：活动/更新日期可伪装发布时间，真实发布时间遗漏。

建议：只有明确发布证据才写 published_at，updated_at 独立；适配 發佈日期· 等真实格式，并覆盖通用和回退两条解析路径。

### R-007 · P1 · 收藏筛选字段不一致

位置：`app/web/routes/api.py:453; app/services/fare/intel.py:662`。

复现：隔离视图信号 signal_status=bookmarked，行数据没有 user_feedback，feedback=bookmarked 筛选 0 条。

影响：已收藏情报无法按 UI 筛选。

建议：从同一事实字段构造反馈模型，统一写入、读取和 UI 选项；测试实际 API 与按钮。

### R-008 · P1 · 港澳到内地跨境航线被过滤

位置：`app/services/fare/intel.py:565`。

复现：内存数据 HKG→PVG、exclude_domestic=true，经港澳偏好视图输出 0；目的地 PVG 被无条件判为国内。

影响：符合内地出入境要求的跨境机会被漏掉。

建议：以起点与终点组合判断跨境，纯内地对才排除；测试 HKG↔PVG、内地↔内地。

### R-009 · P2 · 目的地及时间筛选存在语义错配

位置：`app/web/routes/api.py:440`。

复现：目的地=香港匹配标题「香港航空 上海→大阪」即使 destination=KIX；date_from 使用 published_at 或 found_at，不是出行日期。

影响：错误匹配目的地，用户无法按出行日期筛选。

建议：以结构化目的地与别名匹配，未知单列；发布、发现、出行日期分别提供明确筛选。

### R-010 · P1 · 抽奖核心推荐只凭来源类型与关键词

位置：`app/services/discovery/service.py:456`。

复现：合成官方候选「中国内地国内航班免费机票抽奖」和「不包括中国大陆出发的国际免费机票抽奖」均标 confirmed_mainland_outbound、core_recommend=true，verify_status=candidate。

影响：将国内航段或明确排除内地出发的活动误报为已确认核心推荐。

建议：证据驱动独立核验奖品、方向、排除条件和来源，必要时 unknown；未经确认不得标 confirmed/core。

### R-011 · P1 · 异步抽奖发现中使用 asyncio.run

位置：`app/services/discovery/service.py:104; app/core/safe_http.py:139`。

复现：在已有 event loop 中调用 discover_official_tourism_events，内部 safe_get_sync 抛 RuntimeError: asyncio.run() cannot be called from a running event loop；被捕获后 AJAX 0 条。

影响：真实异步扫描静默丢失 AJAX 活动候选。

建议：让发现函数异步并 await safe_get，或确保同步 API 不在事件循环运行；错误分层报告而非吞掉。

### R-012 · P1 · 通知成功状态不能跨进程恢复

位置：`app/services/notify/delivery.py:113`。

复现：内存 SQLite 模拟首次 toast 成功；清空 _DELIVERY_STATE 模拟进程重启后同一通知再次调用，console/toast 各执行两次。

影响：重启后重复提醒。

建议：持久化唯一事件键及每渠道成功状态；重启后加载相同事实，避免依赖内存和正文前缀。

### R-013 · P1 · 失败重试次数没有上限

位置：`app/services/notify/delivery.py:118`。

复现：替身 toast 总是 failed，单进程连续调用 5 次均外送；前缀含 a1，解析数字逻辑却判断 meta[1].isdigit()。

影响：重复打扰且超出三次限制。

建议：持久化解析正确的整型 attempts、退避和终止状态，成功后不重试；覆盖同进程与重启。

### R-014 · P1 · 旧版本数据库被错误标记为最新

位置：`app/db/session.py:45; app/web/app.py:29`。

复现：临时 SQLite version=0001_initial、head=0004_source_health，check 返回 ok=true、ensure action=ok；app 中未调用 ensure。

影响：旧库可能未迁移就进入运行；本次未操作实际用户库。

建议：显式比较当前版本与 head，缺版本、过旧、未知 head/读取错误分别阻断或明确告警；在 Web/CLI 启动接线；先隔离副本验证迁移并备份。

### R-015 · P2 · 已存在内容仍被来源健康标为零解析

位置：`app/services/discovery/service.py:785; app/services/ops/source_health.py`。

复现：模拟第二次解析 1 条已存在：返回 status=ok_existing，但 source.last_result=ok_zero，健康统计会计入零解析。

影响：运营指标与调用结果不一致。

建议：分别持久化解析数、新增数、已有数和 last_result；source-health 识别 ok_existing。

### R-016 · P2 · 确认行程忽略关闭机票监控设置

位置：`app/services/trips/service.py:110; app/services/trips/service.py:180`。

复现：Settings.auto_attach_fare_watch_to_new_trip=false，首次 confirm_trip 后 benefit_discovery 和 fare_monitor 均 enabled=true。

影响：用户关闭该功能仍可能被开启。

建议：恢复和注册分别尊重 task_type 的配置、历史暂停原因及全局设置；覆盖首确认、重复确认、取消和历史订阅。

### R-017 · P2 · PowerShell 子进程输出解码异常

位置：`app/services/notify/delivery.py:51`。

复现：248 单元通过但出现多条 PytestUnhandledThreadExceptionWarning：subprocess readerthread UnicodeDecodeError gbk，输出共 11 warnings。

影响：通知错误输出可能丢失或被误判，测试噪声掩盖实际故障。

建议：明确 subprocess 输出编码及错误处理，隔离测试替换真实 toast；覆盖中文和异常流。

## 下一轮集中整改建议

建议把下列工作作为一批完成，最后统一提交独立复验；不需要每修一项就来回交接。保持现有产品定位、不引入未授权来源、不绕过 robots/CAPTCHA、不自动报名或支付，不重置 72h 观察。涉及数据库结构的工作先做可审阅迁移与隔离验证，正式库操作由用户授权。

### Q1 · 覆盖 R-001, R-002, R-003, R-011

实施：统一安全抓取及异步调用。先验证每跳再 robots；对 403/429/失败停止；连接使用经验证 IP 且保留 HTTPS 主机/TLS 验证，robots 和正文流式限量；异步入口只 await。

验收：模拟公开跳私网时包括 robots 在内无私网请求；DNS 重绑定、重定向环、超大无长度、robots 403/429/异常均 fail closed；合法公开内容及异步 AJAX 可用。

### Q2 · 覆盖 R-004, R-005, R-006, R-007, R-008, R-009

实施：以原文证据绑定路线和金额，明确币种及日期含义，建立对应筛选和反馈字段；修复跨境航线过滤。

验收：真实 FlyNext 及合成台湾800/大阪1500最终界面不串价；MOP/HKD、未知/更新/发表时间、HKG↔PVG、收藏筛选、航司名不作目的地均端到端验证。

### Q3 · 覆盖 R-010, R-016

实施：抽奖适用性保留证据、否定和三态；行程订阅状态遵守全局和任务级设置。

验收：国内航段、明确不包含中国大陆均不核心；仅官方可核实的内地出境正例进入核心；缺国籍/居住 unknown；关闭 fare_monitor 时确认、重确认与恢复不启用。

### Q4 · 覆盖 R-012, R-013, R-015, R-017

实施：事件和渠道状态采用独立、持久、可查询记录；修复重试与状态统计，安全处理 pwsh 文本编码。

验收：模拟成功后进程重启不重复；失败三次后终止，恢复条件明确；长正文不损状态；ok_existing 不计零解析；中文错误输出不触发解码异常。

### Q5 · 覆盖 R-014, B8

实施：将迁移检查接入所有启动入口，按实际版本判定；补真正旧 schema 的隔离备份与升级演练，不操作正式库。

验收：新库、无版本旧库、落后版本、未知版本、迁移异常、升级后恢复都有结果；单元与端到端使用业务数据断言，最后一次性独立复验。

跨站转载合并仍按保守、可追溯策略处理，无法确认同一事件时不强行合并；真实来源、104 项逐条验收与 72h 持续证据继续如实标记，不用 mock 或 HTTP 200 冒充业务成功。

## 执行记录

- PowerShell 7: git rev-parse HEAD; git ls-remote origin refs/heads/develop
- PowerShell 7: .venv/Scripts/python.exe -B -m pytest tests/unit -q -p no:cacheprovider → 248 passed, 11 warnings in 17.62s
- Python stdin: httpx MockTransport redirects/robots/stream; no real private network request
- Python stdin: SQLite :memory: fare materialization, feedback, cross-border, trip state, giveaway and mock notifications
- Python stdin: temporary isolated SQLite 0001_initial vs 0004_source_health migration checker; no private DB
- Python stdin: HttpxFetchAdapter obeying robots read-only FlyNext homepage; isolated in-memory business pipeline
- Static review of safe_http, adapters, UI/API, eligibility, notifications, Alembic and tests; independent full migration drill, 72h, 104 items NOT_TESTED

结构化状态、缺陷与集中整改包见 `CODEX_AUDIT_MATRIX.json`。本次只更新这两份审计文件，未更改源码、未迁移私人库、未推送。
