# FlightHunter · Codex B1–B8 第二轮集中整改验收

- **日期：** 2026-10-30  
- **基线：** Codex 独立审计 `CODEX_INDEPENDENT_AUDIT.md` / `ac0c447` 业务代码  
- **测试：** **248 passed**（`tests/unit`，含 `test_codex_batch_b1_b8.py`）  
- **原则：** 不宣称完整 V1.0；不自签 Codex 关单；不碰正式库 / 不重置 OBSERVATION  

## 对照整改包

| 包 | 覆盖 | 本轮落地 | 状态 |
|---|---|---|---|
| **B1 安全访问** | N-001, N-002, N-015 | `safe_http` 每跳 URL+DNS 公网校验、Content-Length/体积上限、robots；probe/OCR/AJAX/入口 `_fetch_bytes`/intel 抽样/CLI 证据抓取全部改 `safe_get`；toast 用 **pwsh** + Base64 | **完成**（Mock 重定向/过大拒绝） |
| **B2 语义** | N-003–006, N-008 | 出发地仅显式方向；Peach 不映射 HKG；HK Express 品牌不被孤立内地城市抢跑；多目的地就近绑定/不完整不绑价；立省/最多減等不写 `reported_total`；仅发布标签写 `published_at`；社区 flash → `community_deal_tip` | **完成主路径** |
| **B3 频道筛选** | N-003, N-018 | API 增 `destination/category/date_from/date_to/feedback`；UI 目的地/类别/时间/反馈控件；缺失字段不误作匹配 | **完成** |
| **B4 行程状态机** | N-007 | 已确认编辑不因关闭重扫停用；`confirm_trip` 幂等恢复 `trip_not_confirmed` 订阅；demo/未确认仍禁 | **完成** |
| **B5 证据诚实** | N-009, N-012, N-013, N-016 | 缺国籍/居住 → unknown；campaign 非 verified 显示「线索/待核实」；`auto_extracted_count`；官方源+内地出境表述才可 `core_recommend=True` | **完成主路径** |
| **B6 来源/通知** | N-010, N-011, N-014 | 事件键+送达状态；成功幂等；失败限次重试（`[D:fail:aN:k…]`）；`ok_existing` vs `ok_zero`；跨站合并仍保守 PARTIAL | **部分**（合并有意保守） |
| **B7 迁移可靠性** | N-017 | `check_alembic_head` / `ensure_migrations_or_warn`；隔离演练 `scripts/isolated_migrate_drill.py`：新库→无版本旧库→备份→`upgrade head` → 版本匹配；默认不自动改正式库 | **完成演练** |
| **B8 统一验收** | — | 本报告 + 248 测试 + 回归清单 | **本文件** |

## 关键实现

1. **`app/core/safe_http.py`**：逐跳 `assert_public_http_url` + 生产路径 DNS；体积预检；`safe_get_sync` / `safe_fetch_bytes_sync`。  
2. **`extract_origin_iatas_from_title`**：显式出发优先；品牌与目的地不作为出发证据。  
3. **`extract_route_price_candidates`**：多目的地价格就近绑定；不完整则不写票价。  
4. **`_extract_published_only`**：旅行/出发/销售日期不写入 `published_at`。  
5. **fare API/UI 筛选**：目的地、类别、时间、反馈。  
6. **通知**：事件键；成功 `[D]`；失败可重试至 3 次；pwsh toast。  
7. **迁移**：启动/CLI 可查版本；正式库需用户授权后 `alembic upgrade head`。

## 回归证据（本轮）

| 场景 | 结果 |
|---|---|
| Mock：public→127.0.0.1 | 拒绝 |
| Mock：Content-Length 超限 | 拒绝 |
| 上海→香港 | 出发 PVG，非 HKG 优先 |
| Peach 大阪→首尔 | 无 HKG |
| 立省 HK$800 | `reported_total is None` |
| 旅行日期 | `published_at is None` |
| 發布 2026-10-29 | 写入 published |
| 缺 nationality/residence | eligibility unknown |
| 社区 flash_sale | `community_deal_tip` |
| 隔离迁移演练 | head 匹配，备份存在 |
| 全量 unit | **248 passed** |

## 仍 PARTIAL / NOT_TESTED（诚实边界）

| 项 | 说明 |
|---|---|
| N-008 跨站改写合并 | 仍保守，避免误合并（有意） |
| N-014 事件级合并 | PARTIAL |
| DNS 重绑定连接层绑 IP | 已做每跳解析校验；未做 connect-to-validated-IP 全绑定 |
| 真实 toast 第二次不响 | 需桌面环境人工点验 |
| FlyNext 真源全链路 | 依赖外网时点 |
| 104 项清单 / 72h 连续 | 未在本轮伪装完成 |
| 公网 SaaS 上线 | 不在 V1 范围 |

## 三问

**A. 个人日常试用？**  
**更近，但仍非正式关单**：SSRF 旁路、出发地误判、减免当票价、旅行日期当发布、确认停扫、通知重复/失败不重试、筛选闭环已修主路径；真实网络/桌面 toast/长跑稳定性仍待 Codex 与用户实机。

**B. Codex 缺陷独立复验？**  
**0 / 本轮待复验**。248 测试 ≠ Codex 关单。

**C. 完整 V1.0？**  
**未宣称完成**。跨源合并保守、公网、72h 连续证据仍在。

## 交付

- 代码提交：见本批 `fix(codex-b1-b8)` / `docs` 提交  
- 隔离演练：`scripts/isolated_migrate_drill.py`  
- 建议 Codex 复验快照：`git archive HEAD`  

**不宣称** Codex 已 PASS；等待独立复验。
