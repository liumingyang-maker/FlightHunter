# FlightHunter · 日常使用验收（72 小时目标 / 实际观测窗口）

- **报告 HEAD：** `a405b55`  
- **提交关系：** `651dce7` ⊂ `c57722a` ⊂ `a405b55`（无回退）  
- **测试：** 209 passed  
- **备份：** `backups/fh_daily_20261030_115818.db` · `flighthunter_develop_20261030_111851.bundle` / `…_115818.bundle`  
- **安全：** 无 push / 无合并 main / 不绕过 robots  

---

## 1. 实际观测窗口（诚实）

| 项 | 值 |
|---|---|
| 观测开始（本地） | **2026-10-30 11:52**（约 UTC 03:52） |
| 报告撰写（本地） | **2026-10-30 12:05** |
| **本会话有效墙钟观测** | **≈ 13–15 分钟** |
| 72 小时连续跑 | **本回合无法空等 72h**；已部署可跨会话运行 |

**持续运行部署（真实个人用法）：**
- Worker 进程：`app.cli worker --execute --config data/daily_usage/config.yaml --interval-seconds 1800`（启动时已拉起）
- 登录启动项：`Startup\FlightHunterWorker.bat`（interval 3600，使用 daily 配置）
- 观测配置：`data/daily_usage/config.yaml` → 独立库 `fh_daily.db`

中断/关机/休眠时间 **未** 计入连续运行成功；72h 达成需用户保持开机登录后的 **后续墙钟时间**。

---

## 2. 来源真实统计（已修正口径）

**修复：** `last_fetch_at` 仅在成功读取时更新；新增 `last_attempt_at` / `last_success_at` / `last_valuable_at` / `last_result`。  
**API/CLI：** `GET /api/v1/ops/source-health` · `python -m app.cli source-health`

### 本轮（daily 库首次完整扫描窗口）示例计数

| 口径 | 数量（本轮扫描后峰值） |
|---|---:|
| fare 来源总数 | 9 |
| 历史曾成功（historically_fetched） | 6 |
| 本轮成功读取 | 3（smzdm×2 + OMAAT 或 VFTW 等） |
| 本轮失败 | 3（Fly4Free、Google News×2 → robots/防护） |
| 本轮冷却跳过 | 3+（随后轮次） |
| 本轮有价值 | 2–3（写入信号>0） |
| 窗口内新建 fare 信号 | **22** |

**不是**「9 个里 8 个本轮都成功」——与旧报告错误口径已区分。

---

## 3. 情报质量抽查（≥10）

样本文件：`data/daily_usage/quality_samples.json`

| 检查 | 结果 |
|---|---|
| 抽查条数 | **12** |
| 原始链接可访问 | **12/12 HTTP&lt;400** |
| 城市匹配分级 | `explicit_city`（如成都-赫尔辛基 TFU）、`national_multi_city_pending`（全国多地）、`origin_unknown` |
| 国内航线误入 | 未发现已解析机场对的纯国内对；无机场的全国促销单独保留 |
| 重复推送 | 本轮以单源为主；合并逻辑单测通过 |
| 明显过期标题 | 由 `hide_expired` + 「过期」关键词过滤 |

**样例（真实 smzdm 链接）：**
1. 北上广/成都 → 赫尔辛基 2.7K+（TFU 显式匹配）  
2. 全国多地 → 曼谷/普吉 499+  
3. 全国多地 → 塞尔维亚 3.1K+  

**已修缺陷：** 标题中的 `MAX`/`CEO` 被误当 IATA → 已加入噪声词表；失败成功后 `consecutive_failures` 未清零 → 已修。

---

## 4. 用户体验（Playwright）

截图：`data/daily_usage/ui/daily_fare.png` · `daily_fare_mobile.png` · `daily_notifications.png`

| 项 | 结果 |
|---|---|
| 默认勾选 CKG | **是** |
| 情报列表可见 | **13** |
| 收藏按钮 | **点击成功**（按钮禁用） |
| 手机 390 宽 | 出发地面板可见 |
| 通知页 | 可打开 |

---

## 5. 断网/失败恢复（隔离注入）

将 View from the Wing 指向 `http://127.0.0.1:9`（被 SSRF 防护正确拒绝）：

| 步骤 | 结果 |
|---|---|
| 注入失败 | `last_result=failed`，`consecutive_failures≥1` |
| 恢复真实 URL 并重扫 | `last_result=ok_zero/ok`，`last_success_at` 更新 |

**未**对正式库做破坏性故障注入。

---

## 6. 数据库备份与恢复

| 备份 | 结果 |
|---|---|
| `fh_daily_20261030_115818.db` | 打开成功，sources 可读 |
| develop git bundle ×2 | 已生成 |
| 恢复演练 | 从备份打开只读成功 |

---

## 7. 通知

- 情报模式下优先本地列表；错价高优先级逻辑保留在分类/优先级中  
- 本观测窗口 **未** 产生新的错价类推送（无真实 bug fare 入库）  
- 普通促销：Web 列表 + 后续摘要依赖 worker 持续运行  

---

## 8. 本回合修复的缺陷

1. 来源成功/失败统计混淆（last_fetch 在失败路径也更新）  
2. IATA 把 MAX/CEO 当成机场码  
3. 历史成功被算成本轮成功  
4. 失败恢复后失败计数残留（existing candidate 路径）  
5. 情报页缺少收藏/已读反馈入口（已加 API+UI）  
6. 鉴权 state_dir 相对路径未相对 project_root 解析  

---

## 9. 剩余影响日常使用的问题

1. **72h 连续墙钟** 需关机/休眠外的自然时间；本报告只覆盖 ~15 分钟主动观测 + 已部署后台  
2. Fly4Free / 部分 Google News **robots** 不可用  
3. 发布时间字段：社区列表常为 null，仅有系统发现时间  
4. 全国促销无机场码时无法精确到 CKG/TFU（已用 `city_match_level` 标注，不硬匹配）  
5. 开机计划任务无管理员权限 → 依赖启动文件夹  

---

## 10. 结论

FlightHunter **已按真实个人用法**在隔离日常库上跑通：自动扫描 → 来源健康分口径 → 中国出发国际情报展示 → 链接可点 → 收藏/已读 → 失败退避与恢复 → 备份。  

**不能**在单次会话内用空等证明 72 小时连续成功；Worker 与启动项已挂上，后续应以 `source-health` 与 `OBSERVATION.json` 的自然时间继续累计。  

Git：`develop` @ `a405b55` · 未 push · 未合并 main。
