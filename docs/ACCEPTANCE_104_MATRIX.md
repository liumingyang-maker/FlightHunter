# FlightHunter 104 项验收矩阵

**口径：** PASS 需证据；NOT_TESTED 诚实标注；禁止假绿。
**条数：** 104

| ID | 类别 | 用例 | 方法 | 状态 | 证据 |
|---|---|---|---|---|---|
| T01 | P1-情报 | 出发地多选默认 CKG/TFU/CTU | 单测/标注样本/API | PASS | tests/unit/test_channels.py / airports |
| T02 | P1-情报 | 出发地可增删内地机场 | 单测/标注样本/API | NOT_TESTED | — |
| T03 | P1-情报 | 全国出发仅内地不含 HKG/MFM | 单测/标注样本/API | PASS | tests/unit/test_p1_fare_samples.py::test_hk_mo_not_merged_into_mainland |
| T04 | P1-情报 | HKG/MFM 独立勾选不自动并入 | 单测/标注样本/API | NOT_TESTED | — |
| T05 | P1-情报 | 国际航线过滤（排除纯内地） | 单测/标注样本/API | NOT_TESTED | — |
| T06 | P1-情报 | HKG↔PVG 跨境保留 | 单测/标注样本/API | PASS | tests/unit/test_p1_fare_samples.py::test_q2_cross_border |
| T07 | P1-情报 | 全球错价频道无默认偏好 | 单测/标注样本/API | NOT_TESTED | — |
| T08 | P1-情报 | 四频道切换加载正确 | 单测/标注样本/API | NOT_TESTED | — |
| T09 | P1-情报 | 情报分类：错价/漏油/促销/社区 | 单测/标注样本/API | NOT_TESTED | — |
| T10 | P1-情报 | 社区 flash 不标官方促销 | 单测/标注样本/API | PASS | tests/unit/test_codex_batch_b1_b8.py::test_community_flash_not_official |
| T11 | P1-情报 | 报道价≠可买价文案 | 单测/标注样本/API | NOT_TESTED | — |
| T12 | P1-情报 | 无实时报价仍可用 | 单测/标注样本/API | NOT_TESTED | — |
| T13 | P1-情报 | 来源链接可点击原文 | 单测/标注样本/API | NOT_TESTED | — |
| T14 | P1-情报 | 危险协议链接过滤 javascript: | 单测/标注样本/API | NOT_TESTED | — |
| T15 | P1-情报 | XSS 标题不执行 | 单测/标注样本/API | PASS | tests/unit/test_neutral_audit.py::test_xss_script_in_title_parsed_not_executed |
| T16 | P1-情报 | 过期情报可隐藏 | 单测/标注样本/API | NOT_TESTED | — |
| T17 | P1-情报 | 收藏反馈写入 signal_status | 单测/标注样本/API | NOT_TESTED | — |
| T18 | P1-情报 | 反馈筛选 bookmarked 命中 | 单测/标注样本/API | PASS | tests/unit/test_codex_batch_b1_b8.py::test_b3_api_filter_helper |
| T19 | P1-情报 | 目的地筛选不匹配航司名 | 单测/标注样本/API | PASS | tests/unit/test_neutral_audit.py + q1_q5 dest filter |
| T20 | P1-情报 | 类别筛选 | 单测/标注样本/API | NOT_TESTED | — |
| T21 | P1-情报 | travel 日期窗口重叠 | 单测/标注样本/API | PASS | tests/unit/test_p1_fare_samples.py::test_travel_filter_window_overlap |
| T22 | P1-情报 | 发布/发现/旅行分列 | 单测/标注样本/API | NOT_TESTED | — |
| T23 | P1-情报 | 裸日期不写 published_at | 单测/标注样本/API | PASS | scripts/label_samples.py 裸日期样本 |
| T24 | P1-情报 | 发佈日期标签写 published_at | 单测/标注样本/API | PASS | scripts/label_samples.py 發佈日期样本 |
| T25 | P1-情报 | 多目的地多价不写单一票价 | 单测/标注样本/API | PASS | scripts/label_samples.py 多价样本 34/34 |
| T26 | P1-情报 | MOP≠HKD 币种 | 单测/标注样本/API | PASS | tests/unit/test_codex_q1_q5.py::test_q2_mop_currency |
| T27 | P1-情报 | 立省/最多減不写票价 | 单测/标注样本/API | PASS | scripts/label_samples.py 立省/最多減 |
| T28 | P1-情报 | 20KG 不作 20000 | 单测/标注样本/API | PASS | scripts/label_samples.py 20KG |
| T29 | P1-情报 | 品牌航司不证明出发地 | 单测/标注样本/API | PASS | tests/unit/test_neutral_audit.py::test_origin_empty_on_pure_brand |
| T30 | P1-情报 | 去重合并保守不误合并 | 单测/标注样本/API | PASS | tests/unit/test_a_core_e2e.py::test_merge_intel_signals_conservative |
| T31 | P2-抽奖 | 候选 materialize 不进 core | 单测/服务流 | PASS | materialize core_recommend=False 静态+测试 |
| T32 | P2-抽奖 | 国内航班不 core | 单测/服务流 | PASS | tests/unit/test_p2_core_recommend.py::test_domestic_word_never_core |
| T33 | P2-抽奖 | 排除大陆不 core | 单测/服务流 | PASS | tests/unit/test_p2_core_recommend.py::test_excluded_never_core |
| T34 | P2-抽奖 | candidate 不 core | 单测/服务流 | PASS | tests/unit/test_p2_core_recommend.py::test_candidate_never_core |
| T35 | P2-抽奖 | 社区源不 core | 单测/服务流 | PASS | tests/unit/test_p2_core_recommend.py::test_non_official_source_never_core |
| T36 | P2-抽奖 | 官方+国际+内地出境可 core | 单测/服务流 | PASS | tests/unit/test_p2_core_recommend.py::test_positive_requires_international_and_official |
| T37 | P2-抽奖 | human_review 降级 core | 单测/服务流 | PASS | tests/unit/test_a_core_e2e.py::test_core_e2e_demote_on_human_review |
| T38 | P2-抽奖 | closed/unknown 降级 core | 单测/服务流 | PASS | tests/unit/test_a_core_e2e.py::test_core_demote_not_open |
| T39 | P2-抽奖 | 资格缺国籍/居住→unknown | 单测/服务流 | PASS | tests/unit/test_codex_q1_q5.py::test_q3 / eligibility |
| T40 | P2-抽奖 | 资格冲突→ineligible | 单测/服务流 | PASS | tests/unit/test_eligibility.py |
| T41 | P2-抽奖 | 年龄无官方规则→unknown | 单测/服务流 | PASS | multi_round age unknown |
| T42 | P2-抽奖 | 页面 verify/类型/出境/核心分栏 | 单测/服务流 | PASS | campaigns.html 分栏 + pages |
| T43 | P2-抽奖 | demo 标 fixture | 单测/服务流 | PASS | campaigns.html demo=fixture |
| T44 | P2-抽奖 | 非 verified 标待核实 | 单测/服务流 | PASS | campaigns.html candidate/待核实 |
| T45 | P2-抽奖 | 官方链接 vs 线索链接 | 单测/服务流 | NOT_TESTED | — |
| T46 | P2-抽奖 | OCR 日期解析（海报） | 单测/服务流 | NOT_TESTED | — |
| T47 | P2-抽奖 | HTML/OCR 冲突→人工复核 | 单测/服务流 | NOT_TESTED | — |
| T48 | P2-抽奖 | entry probe 不登录不提交 | 单测/服务流 | NOT_TESTED | — |
| T49 | P2-抽奖 | robots 拒绝时 blocked | 单测/服务流 | NOT_TESTED | — |
| T50 | P2-抽奖 | 自动核验命名 auto_extracted | 单测/服务流 | NOT_TESTED | — |
| T51 | P3-行程 | 未确认不扫描 | 矩阵测试 | PASS | tests/unit/test_p3_trip_matrix.py |
| T52 | P3-行程 | demo 不可确认 | 矩阵测试 | PASS | test_p3_trip_matrix.py::test_demo_cannot_confirm |
| T53 | P3-行程 | 确认后订阅启用 | 矩阵测试 | PASS | test_p3_trip_matrix.py 确认启用 |
| T54 | P3-行程 | 确认恢复 trip_not_confirmed | 矩阵测试 | PASS | test_p3_trip_matrix.py::test_confirm_restores_trip_not_confirmed |
| T55 | P3-行程 | 已确认编辑不扫停 | 矩阵测试 | PASS | test_p3_trip_matrix.py::test_confirmed_edit_rescan_off_keeps_enabled |
| T56 | P3-行程 | auto_scan_off 不禁用已有 | 矩阵测试 | PASS | 同上 |
| T57 | P3-行程 | fare_monitor 尊重 auto_attach | 矩阵测试 | PASS | test_p3_trip_matrix.py::test_confirm_respects_fare_watch_off |
| T58 | P3-行程 | 取消行程停订阅 | 矩阵测试 | PASS | test_p3_trip_matrix.py::test_cancel_disables_all |
| T59 | P3-行程 | 日期校验 end>=start | 矩阵测试 | PASS | tests/unit/test_neutral_audit2.py::test_trip_date_validation |
| T60 | P3-行程 | 行程福利匹配国家 | 矩阵测试 | NOT_TESTED | — |
| T61 | P3-行程 | 城市匹配 unknown 不假匹配 | 矩阵测试 | NOT_TESTED | — |
| T62 | P3-行程 | 日期窗口相交 | 矩阵测试 | NOT_TESTED | — |
| T63 | P3-行程 | 城市停留日相交 | 矩阵测试 | NOT_TESTED | — |
| T64 | P3-行程 | 社区 travel_deal 无国家不全国 | 矩阵测试 | NOT_TESTED | — |
| T65 | P3-行程 | 领取记录不被编辑清空 | 矩阵测试 | NOT_TESTED | — |
| T66 | 安全 | 私网 URL 拒绝 | 中立审计/单测 | PASS | test_neutral_audit.py::test_url_safety_rejects_metadata |
| T67 | 安全 | 169.254.169.254 拒绝 | 中立审计/单测 | PASS | 同上 169.254 |
| T68 | 安全 | 数字 IP 别名拒绝 | 中立审计/单测 | PASS | test_p0_browser_safety.py 数字别名 |
| T69 | 安全 | 共享地址 100.64 拒绝 | 中立审计/单测 | PASS | test_p0_browser_safety.py::test_shared_address_space_blocked |
| T70 | 安全 | 公开→私网重定向拒绝且无请求 | 中立审计/单测 | PASS | test_neutral_audit.py::test_safe_get_no_follow_to_private |
| T71 | 安全 | robots 403 fail-closed | 中立审计/单测 | PASS | test_codex_q1_q5.py::test_q1_robots_403_fail_closed |
| T72 | 安全 | robots 429 fail-closed | 中立审计/单测 | NOT_TESTED | — |
| T73 | 安全 | 流式超限拒绝 | 中立审计/单测 | PASS | test_q1_stream_too_large |
| T74 | 安全 | Content-Length 超限拒绝 | 中立审计/单测 | NOT_TESTED | — |
| T75 | 安全 | URL 内嵌凭据拒绝 | 中立审计/单测 | PASS | url_safety credentials |
| T76 | 安全 | 同源请求也 DNS 校验 | 中立审计/单测 | PASS | test_c14_browser_doctor.py::test_same_origin_also_validated |
| T77 | 安全 | 弹窗默认拒绝 | 中立审计/单测 | PASS | test_c14_browser_doctor.py::test_popup_handler_rejects |
| T78 | 安全 | 浏览器私网目标拒绝 | 中立审计/单测 | PASS | test_p0_browser_safety.py private |
| T79 | 安全 | safe_get 在 loop 内安全 | 中立审计/单测 | PASS | test_codex_q1_q5.py::test_q11 / safe_get_sync |
| T80 | 安全 | pwsh 非 powershell 5.1 | 中立审计/单测 | PASS | delivery.py pwsh |
| T81 | 安全 | toast Base64 传参无拼接注入 | 中立审计/单测 | NOT_TESTED | — |
| T82 | 安全 | subprocess UTF-8 解码 | 中立审计/单测 | PASS | delivery.py UTF-8 |
| T83 | 安全 | 无 shell=True | 中立审计/单测 | PASS | test_neutral_audit.py::test_subprocess_no_shell_true |
| T84 | 安全 | 无 eval/exec | 中立审计/单测 | PASS | test_neutral_audit.py::test_no_eval_in_app |
| T85 | 安全 | 无 f-string SQL | 中立审计/单测 | PASS | test_neutral_audit.py::test_sqlalchemy_no_raw_fstring_in_app |
| T86 | 通知/来源 | 通知成功幂等不重复 | 单测/日志 | PASS | test_q4_delivery_persists_and_limits |
| T87 | 通知/来源 | 失败重试≤3 | 单测/日志 | PASS | 同上 attempts≤3 |
| T88 | 通知/来源 | 事件键跨进程持久 | 单测/日志 | PASS | NotificationDelivery 持久表 |
| T89 | 通知/来源 | 长正文状态不丢 | 单测/日志 | NOT_TESTED | — |
| T90 | 通知/来源 | ok_existing≠ok_zero | 单测/日志 | PASS | ok_existing vs ok_zero |
| T91 | 通知/来源 | ok_valuable 计有价值 | 单测/日志 | NOT_TESTED | — |
| T92 | 通知/来源 | source_health 区分 existing | 单测/日志 | PASS | source_health round_existing |
| T93 | 通知/来源 | 失败来源 consecutive_failures | 单测/日志 | NOT_TESTED | — |
| T94 | 通知/来源 | 403/429 停抓 | 单测/日志 | NOT_TESTED | — |
| T95 | 通知/来源 | Worker 单实例锁 | 单测/日志 | PASS | worker_lock 单实例 |
| T96 | 运行/Web | Web 启动不改旧库表 | 隔离冒烟/Playwright/72h | PASS | smoke_after_codex_merge.py 旧库不变 |
| T97 | 运行/Web | doctor 只读 | 隔离冒烟/Playwright/72h | PASS | test_c14_browser_doctor.py::test_doctor_readonly_no_init_db |
| T98 | 运行/Web | 迁移 outdated 提示 | 隔离冒烟/Playwright/72h | PASS | check_alembic_head outdated |
| T99 | 运行/Web | 迁移 in_sync | 隔离冒烟/Playwright/72h | PASS | isolated_migrate_drill.py |
| T100 | 运行/Web | CLI report_migration 可见 | 隔离冒烟/Playwright/72h | PASS | report_migration 接线 |
| T101 | 运行/Web | Web 四频道页可用 | 隔离冒烟/Playwright/72h | NOT_TESTED | — |
| T102 | 运行/Web | campaigns 分栏可用 | 隔离冒烟/Playwright/72h | NOT_TESTED | — |
| T103 | 运行/Web | 登录后私有数据 | 隔离冒烟/Playwright/72h | NOT_TESTED | — |
| T104 | 运行/Web | 72h 连续采样报告 | 隔离冒烟/Playwright/72h | NOT_TESTED | — |

## 汇总

- **NOT_TESTED**: 37
- **PASS**: 67