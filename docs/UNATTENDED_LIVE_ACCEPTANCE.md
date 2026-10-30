# FlightHunter · 无人值守真实业务闭环验收

- **时间（UTC）**：2026-10-30
- **Git HEAD**：`2c33189`（其上为 `f1b6366` 文档、`9bdfbba` OCR 证据管道）
- **HEAD 关系**：用户汇报 `f1b6366` 与报告中的 `9bdfbba` **都是当前历史祖先**；`9bdfbba` 为证据管道功能提交，`f1b6366` 为其后的验收文档，`2c33189` 为本次无人值守接入。**未回退、未覆盖。**
- **环境**：PowerShell 7 · `uv` venv · Tesseract 5.4
- **测试**：`pytest tests/unit` → **200 passed** · ruff 通过
- **安全**：无外站报名提交、无 push、无合并 main

---

## 1. 真正的全自动流水线（任务一）

### 隔离环境

| 项 | 值 |
|---|---|
| 配置 | `%TEMP%\fh_unattended\config.yaml` |
| 数据库 | `…\fh_unattended\data\unattended.db` |
| **来源（初始）** | **仅** `VISITKOREA 中文美食栏目` → `chinese.visitkorea.or.kr/svc/sp/food` |
| 未注入 | 活动 ID、详情 URL、日期、手工 JSON **均未配置** |
| 启动入口 | `python -m app.cli worker --once --execute --config …`（正常调度入口） |

### 流水线实测结果

```
worker --execute → run_due_scans(include_raffle_pipeline=True)
  → run_raffle_pipeline
    → run_discovery(module=raffle)          # 扫描美食栏目
    → 发现 contentsView 链接（含 vcontsId=1594420）
    → fetch 详情页 → 下载海报 → OCR
    → extract_official_evidence → 入库 evidences
    → 开放状态判定 → 六态 tags
    → 低频探测报名入口 event.do
  → Web/API open_only 展示
```

| 步骤 | 结果 |
|---|---|
| 公开来源扫描 | 成功（`last_fetch_at` 已更新） |
| 活动链接发现 | **成功**（14 条 official_url 轮次） |
| 详情访问 + 海报 OCR | **成功** |
| 官方规则证据入库 | `evidences` 中 `auto.*` 字段 |
| 日期状态 | LOCAL AIRPORT → **open** 2026-10-26～11-22 |
| 用户资格评估 | **unknown / false**（无真实档案） |
| Web 展示 | `open_only&flight_only` → **1** 条 LOCAL AIRPORT；截图 `data/korea_recheck/web_unattended.png` |

**LOCAL AIRPORT FOOD（1594420）无人工参数链路：已跑通。**

**仍依赖人工的环节：**

| 环节 | 原因 |
|---|---|
| 页脚/条款类链接的规则解读 | OCR/HTML 无完整活动字段 → `human_review` |
| 中文奖品人数等 | 见多语言 OCR |
| 最终报名提交 | 产品策略禁止自动提交 |
| 真实用户资格 | 无国籍/居住档案 |

---

## 2. 多语言 OCR（任务二）

| 项 | 结果 |
|---|---|
| 语言检测 | `detect_text_lang`（html lang + CJK/假名/谚文统计） |
| 语言包序列 | zh→`chi_sim+eng`，ja→`jpn+eng`，ko→`kor+eng`，en→`eng` |
| 本机已装 | **仅 eng/osd**（chi_sim 下载曾失败） |
| 实测日期 | **eng OCR 成功**：`2026.10.26 ~ 2026.11.22`（海报） |
| 中文奖品人数 | **未识别完整** → `human_review_required=true`，**不**因有 OCR 文本就标 high |
| 可信度规则 | 仅当 OCR 解析出完整日期模式才对日期字段标 high；否则 medium/low/pending |
| HTML vs OCR 冲突 | 写入 `conflict_notes`，相关证据降为 `pending`，进人工复核，**不自动择优** |
| 视觉大模型复核 | 本机无授权视觉 API → **未启用**（不把个人信息/私图外发） |
| 日/韩 | 逻辑已支持；本轮无日韩海报样本 → 未报成功 |

---

## 3. 报名入口 504（任务三）

| 探测方式 | 结果 |
|---|---|
| 直接 GET `event.do?id=4d3e8abd-…`（httpx，早前） | **HTTP 504** |
| **Playwright 浏览器打开同一 URL（本次）** | **200**，跳转 `surveyIntro.do?srvyKeyCd=4d3e8abd-…` |
| 页面内容 | 标题「LOCAL AIRPORT FOOD…」；须知：**仅限非韩国常住海外游客**；隐私同意；**「参加活动」** 按钮 |
| 是否点最终提交 | **否**（停在同意/参加前） |
| 低频重试 | `ENTRY_PROBE_MIN_INTERVAL_HOURS=6`；本次探测 `entry_operable=true`，`entry_status=http_200_readonly` |

**根因判断（诚实）：**

- **不能确定**为永久故障；更像 **临时 504 / 网关抖动**，或 httpx 与浏览器 TLS/路径差异。  
- 浏览器路径证明入口 **当前可打开问卷/隐私页**。  
- 系统已记录 `entry_url` 并低频探测；恢复后 `entry_operable` 可自动更新。  
- 截图：`data/korea_recheck/entry_browser_status.png` · `entry_browser_result.json`

---

## 4. 长期运行与监控（任务四）

| 机制 | 状态 |
|---|---|
| `worker --execute` 周期循环 | **可用**（`--once` 已实测；可挂任务计划） |
| `scan-due --execute` / API `scheduler/run-due` | 纳入 `include_raffle_pipeline` |
| 开机恢复 | 依赖 Windows 任务计划启动 worker（本机未注册持久任务，**未声称已开机自启**） |
| 来源失败监控 | `consecutive_failures` + monitor 规则 |
| 规则变化 / 截止提醒 | 截止字段入库；临近提醒 **未完整实现**（partial） |
| 重复抑制 | 轮次 edition/program_key + evidence content_hash |
| 六态区分 | `tags.six_state`：http_ok / extract_ok / rules_complete / date_open / entry_operable / user_eligible |
| 业务成功率 | TaskRun `raffle_auto_pipeline` completed 计数 |

**六态实测（LOCAL AIRPORT）：**

```
http_ok=true, extract_ok=true, rules_complete=false,
date_open=true, entry_operable=true, user_eligible=false
```

---

## 5. 安全隔离与鉴权（任务五）

| 检查 | 结果 |
|---|---|
| 测试 Web 是否复用正式 `FlightHunter/data/auth.json` | **否** |
| 机制 | `auth.state_dir`（配置）+ 隔离 SQLite 不在仓库 `data/` 时状态写 DB 同目录 |
| 实测 | `fh_unattended/data/auth.json` token **≠** `FlightHunter/data/auth.json` |
| 日志输出令牌 | **未**打印完整 token（仅前缀调试时截断） |
| 加载代码 | WorkingDirectory=仓库根 → 最新 `app.*` |
| 数据库 | `unattended.db`（隔离） |
| 错误杀进程 | 仅按 `app.cli web` + 配置路径特征停止，不杀无关 PID |
| 正式库覆盖 | 未写主库 |
| 外站提交 | 未执行 |

---

## 6. 三条业务主线（任务六）

| 主线 | 状态 | 说明 |
|---|---|---|
| **全球免费旅行抽奖** | **partial→主流程可跑** | 韩国美食栏目全自动发现+OCR+开放判定+入口探测；美国 Sweepstakes Travel 已抓取候选（聚合无 official_url → 不自动 verified）；日本 japan.travel 首页 0 抽奖；英国 visitbritain **403** 不绕过 |
| **日本 Trip Benefits** | **partial** | 福利候选/指南可用；官方三窗完整核实仍缺；无假领券 |
| **低价机票雷达** | **partial** | 社区信号+过期过滤；**无授权供应商** → 全部 `price_unconfirmed`，不伪造可购价 |

**非韩国真实测试：**

- Sweepstakes Today Travel（US）：成功抓取，轮次入库，无官方 URL 者不进 open 列表  
- japan.travel：200，giveaway 链接 **0**  
- visitbritain：**403**

---

## 7. 交付清单

| 产物 | 路径 |
|---|---|
| 本报告 | `docs/UNATTENDED_LIVE_ACCEPTANCE.md` |
| 隔离库/日志 | `%TEMP%\fh_unattended\`（config/db/auth/worker_*.log） |
| 浏览器证据 | `data/korea_recheck/entry_browser_*` · `web_unattended.png` |
| 提交 | `2c33189`（及 `f1b6366` / `9bdfbba`） |
| 测试 | 200 passed |

---

## 8. 最终结论（真实能力）

**已做到：**

1. 仅配置公开美食栏目源 → `worker --execute` **无人工传参** 完成发现→详情→海报 OCR→证据→开放状态→入口探测→Web 展示。  
2. LOCAL AIRPORT FOOD：**date_open=true**，入口浏览器可进问卷/隐私页，**未提交**。  
3. 测试鉴权与正式库/令牌 **隔离**。  
4. 六态监控字段写入 tags。

**尚未做到 / 仍缺口：**

1. 中文奖品人数等多语言字段仍需人工复核（缺 chi_sim 语言包）。  
2. `rules_complete=false`；`user_eligible=false`。  
3. 报名最终步骤永不自动执行。  
4. 未注册 Windows 开机计划任务（需管理员/用户策略时再说）。  
5. 截止临近提醒、规则 diff 监控为 partial。  
6. 真实机票可购价仍无授权供应商。

Git：`develop` @ `2c33189` · 未 push · 未合并 main。
