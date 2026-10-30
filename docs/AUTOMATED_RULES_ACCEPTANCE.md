# FlightHunter · 真实活动自动核实闭环验收

- **时间（UTC）**：2026-10-30
- **开发 HEAD**：`9bdfbba`（其前序状态模型 `8bade1b`–`b705192`）
- **环境**：PowerShell 7 · 项目 venv（含 pillow / pytesseract）· Tesseract 5.4.0
- **测试库**：`%TEMP%\fh_korea_disc\data\korea.db`
- **Web**：`http://127.0.0.1:8765`（config 指向 korea.db；token=`FlightHunter/data/auth.json`）
- **安全**：只读；无真实报名/付款/个人资料提交

---

## 0. 运行环境核查（任务三）

| 项 | 结果 |
|---|---|
| Git HEAD | `9bdfbba`（develop，ahead of origin） |
| 8765 监听 | Python `app.cli web --config …fh_korea_disc\config.yaml --host 127.0.0.1 --port 8765` |
| 启动方式 | 项目 `.venv` python，**WorkingDirectory=FlightHunter**（保证加载最新 `app.*`） |
| 数据库 | `storage.sqlite_path` → `…\fh_korea_disc\data\korea.db`（隔离，非主库） |
| 鉴权 | `FlightHunter/data/auth.json` 的 `api_token`（`project_root/data/auth.json`） |
| health | 200 `status=up` |
| 旧 ChildProcess.kill | 上次异常为会话中断残留；已按 **korea_disc 配置特征** 定向停止后重启，未误杀无关进程 |

**说明**：`--config` 只覆盖 storage/sources 等；`auth.json` 路径跟随 `project_root`（仓库根），故 Web token 在 `FlightHunter\data\auth.json`。

---

## 1. 自动发现（无人注入活动 ID/URL）

| 项 | 结果 |
|---|---|
| 入口 | `VISITKOREA 中文美食栏目` → `chinese.visitkorea.or.kr/svc/sp/food` |
| 机制 | 解析 `javascript:goLinkPage(... contentsView.do?...vcontsId=…)` |
| **自动发现成功** | **是** — 落库候选 `official_url` 含 `vcontsId=1594420`（标题为栏目卡片文案） |
| 是否硬编码活动 | **否** — 解析器不包含该 ID/日期/奖品常量 |

---

## 2. 自动提取规则（无人工 poster-facts）

**命令**：`raffle-multi-round-check <详情URL> --auto`（**不**传 `--poster-facts-json`）

| 字段 | 自动提取值 | 方法 / 定位 | 可信 |
|---|---|---|---|
| opens | **2026-10-26** | `image_ocr:tesseract:eng` · 海报图 | high |
| closes | **2026-11-22** | 同上 | high |
| entry_period | `2026.10.26 ~ 2026.11.22` | 同上 | high |
| prize_is_flight | true | `html_text` · 正文「往返机票」 | high |
| winners_count | （OCR 中文不清晰） | — | **缺失 → human_review** |
| open_status | **open**（now=2026-10-30） | 日期窗口 | high |
| human_review_required | **true** | 奖品人数等未完全机器读全 | — |
| `manual_poster_facts_used` | **false** | — | — |

**证据行**（已写入 `evidences`，`field_path=auto_extract.*`）：来源 URL=海报/详情页，locator=图/正文，method=OCR/HTML，retrieved_at=本次抓取。

**资产发现**：`discover_page_assets` 识别 `/public/images/…` 海报、规则链接类 `<a>`；自动下载海报并 OCR。

**人工渠道**：`--poster-facts-json` 仍可用，但 **不得** 计入自主提取成功（payload 中 `manual_poster_facts_used=true`）。

---

## 3. 状态字段分离（任务二）

| 字段 | LOCAL AIRPORT FOOD | 说明 |
|---|---|---|
| 活动日期开放 | **是**（10/26–11/22） | `open_status=open` |
| 官方报名通道可进入 | **否 / 未证实** | 详情页内发现 `event.do?id=4d3e8abd-…`，只读 GET → **HTTP 504**；海报「参与活动」非 HTML 控件 |
| 官方规则核实完整 | **部分** | 日期+机票奖品已机器核实；人数/完整条款仍 human_review |
| 用户资格 | **unknown** | 无真实国籍/居住档案 |
| 允许提交报名 | **否** | 配置 `auto_submission_globally_enabled=false`；遇登录/最终提交即停 |

**Web/API**：

- `GET /api/v1/campaign-rounds?open_only=true&flight_only=true` → 含 `[auto_extracted_event] LOCAL AIRPORT FOOD`
- `pending_only=true&flight_only=true` → K-SPICY `survey_roundtrip`
- 浏览器截图：`data/korea_recheck/web_auto_evidence.png`

**中文操作指南（诚实版）**：

1. 打开官方详情页（见 official_url）。  
2. 活动期以海报 OCR 日期为准：**2026-10-26～11-22**。  
3. 报名入口：页面/海报有参与提示，但 **event.do 当前 504**，**不能**视为可提交。  
4. 需登录/同意隐私/答题时由用户自行完成；系统 **不代填、不提交**。  
5. 资格（是否非韩国居民等）以官方全文为准，当前字段 **待核实**。

---

## 4. 六层结果总表（任务五）

| # | 指标 | LOCAL AIRPORT FOOD | 证据 |
|---|---|---|---|
| 1 | **自动发现成功** | **是** | 美食栏目 → goLinkPage → `vcontsId=1594420` 入库 |
| 2 | **自动提取规则成功** | **是**（日期/机票/开放） | `automated_evidence` OCR+HTML；`manual_poster_facts_used=false` |
| 3 | **官方规则核实完成** | **部分** | 人数/完整条款仍 pending；冲突则 human_review |
| 4 | **活动日期开放** | **是** | opens/closes 窗口含 2026-10-30 |
| 5 | **报名入口可操作** | **否** | `event.do` **HTTP 504**；未登录、未提交 |
| 6 | **用户资格通过** | **否** | eligibility=unknown |
| 7 | **实际已报名** | **否** | 无 entry_attempt 提交 |

---

## 5. 全球通用能力（任务四）

| 来源 | 国家 | 结果 |
|---|---|---|
| VISITKOREA 美食/VK Events | 韩国 | 发现+自动提取 **成功**（见上） |
| Sweepstakes Today Travel | 美国/国际聚合 | 已发现多条旅行/机票线索；`open_status=unknown`（无日期）→ **不进 open_only** |
| japan.travel | 日本 | HTTP 200；首页链接扫描 **0** 条 giveaway/contest → **真实零结果** |
| visitbritain.com | 英国 | **403**（Cloudflare）→ 不绕过 |
| visitfinland.com | 芬兰 | 200；短扫描未见抽奖入口 → 零结果 |

**结论**：证据管道为 **站点无关**（HTML 资产 + 图片 OCR + 日期/奖品规则解析）；韩国适配仅体现在 `goLinkPage`/栏目入口，不把具体活动写死进解析器。

---

## 6. 测试与提交

| 项 | 结果 |
|---|---|
| `pytest tests/unit` | **200 passed** |
| 新增 | `tests/unit/test_evidence_extract.py`（资产发现、OCR 文本日期、auto_extract 无硬编码） |
| ruff（业务路径） | 通过 |
| 提交 | `9bdfbba feat(evidence): 通用海报OCR证据管道…` |
| 截图 | `data/korea_recheck/web_auto_evidence.png` · `local_airport_poster.png` · `local_airport_entry_readonly.png` |

---

## 7. 最终结论

### LOCAL AIRPORT FOOD 是否已实现「无人工录入」自动核实闭环？

**核心链路：是。**

1. 从美食栏目 **自动发现** 详情页（无 ID/URL 注入）；  
2. **自动** 发现海报资产并 **OCR** 得到 2026-10-26～11-22；  
3. 结合 HTML 判定 **open + 往返机票**；  
4. 入库并带 `auto_extract.*` 证据行；  
5. **未**使用 `--poster-facts-json`。

**完整闭环仍缺口（诚实）：**

- 报名入口 `event.do` **504**，不能操作报名；  
- 中文奖品人数等 OCR 不全 → `human_review_required`；  
- 用户资格 unknown；  
- 规则全文（PDF/条款页）未全部机读。

### 距离「可实际报名」还缺什么？

1. **报名通道恢复且只读验证可进入**（当前 504）；  
2. **完整官方规则**（人数、税费、使用期、居住限制）机读或人工复核通过；  
3. **真实用户资格**（国籍/居住）已知且评估为 eligible；  
4. 用户本人在官方页完成登录/同意/答题并 **自行提交**（产品仍不自动提交）。

---

Git：`develop` @ `9bdfbba` · 未合并 main · 未 push · 未外站提交。
