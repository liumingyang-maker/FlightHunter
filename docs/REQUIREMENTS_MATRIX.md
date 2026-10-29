# FlightHunter 需求完成矩阵（诚实口径）

**HEAD：** 见 Git `develop`  
**生成时间：** 2026-10-29  
**口径：** `done` = 可调用实现 + 测试/运行证据；`partial` = 有代码未闭环；`blocked` = 外部授权/账号；`not_implemented` = 无有效实现。**测试数量 ≠ 104 项验收通过。**

## 汇总

| 状态 | 约计 |
|---|---|
| done（核心子能力/有证据） | ~40+ |
| partial | 大量（真实外站/供应商/邮箱未全通） |
| blocked | 邮箱 OAuth/IMAP、实时票价供应商、部分站点 |
| not_implemented | 少量深集成（如完整多语言规则引擎） |

## 目标一 · 监控与通知

| ID | 状态 | 证据 |
|---|---|---|
| MON-01 启动脚本 | done | `scripts/install_worker_task.ps1` |
| MON-02 连续扫描 | partial | worker/scan-due 存在；24h 重启未实测 |
| MON-03 租约/幂等 | done（核心） | TaskRun idempotency；dry/execute 分离 |
| MON-04 来源复用 | done（核心） | last_fetch_at 轮询 + 冷却 |
| MON-05 通知送达语义 | done（本地） | console=recorded；toast_delivered |
| MON-06 可观察性 | done | `GET /api/v1/ops/status` |
| MON-07 SSRF 门槛 | partial | 字符串+DNS 预检；连接绑定未完；不可信外链默认关 |

## 目标二 · 三引擎

| ID | 状态 | 证据 |
|---|---|---|
| SRC-01 来源目录 | done | Sources 种子 + 健康字段 |
| SRC-02 抓取解析 | done（公开 HTML） | **实测** smzdm/piao 列表抓取写入 20+ FareDealSignal |
| SRC-03 去重/多语言 | partial | 标题去重；14 语言词表未全 |
| GIV-01~05 | partial/done 子集 | 资格三态、Chromium 模拟站 E2E 已通；真实外站关 |
| TRP-01~06 | partial | 匹配/卡包/指南/演示流有测试；真实来源持续监控 partial |
| FAR-01~05 | partial/done 子集 | 解析风险匹配通知有；真实双人可购报价 **blocked**（无供应商） |

## 目标三 · 浏览器/卡包/邮件/UI

| ID | 状态 | 证据 |
|---|---|---|
| INT-01 浏览器 | done（本地模拟） | Chromium 实测 confirmed+回执 |
| INT-02 邮件 | partial | IMAP 配置接口 + 本地 .eml 扫描；无授权邮箱 |
| INT-03 加密钱包 | done（读写） | DPAPI/AES-GCM + API；密钥备份演练 partial |
| INT-04 UI | done（基础） | 首页/报名/行程/雷达/卡包/提醒/设置 + 鉴权 |
| INT-05 通知落地 | done（站内+toast 尝试） | 手机推送 blocked |
| INT-06 Windows 安装 | partial | 脚本有；干净机全流程未录屏 |

## 安全门槛（不可突破）

- 不自动真实外站提交 / 付款 / 过验证码  
- 模拟回执不写非 demo 活动 confirmed  
- 敏感券码加密；导出无明文  

**不得声称 114/104 全部 done。**
