# FlightHunter 新会话交接摘要

**交接时间：** 2026-11-01  
**当前 HEAD：** `d4b8e35`（develop，与 origin/develop 一致）  
**GitHub：** https://github.com/liumingyang-maker/FlightHunter

---

## 一、项目定位

本地优先的国际机票情报雷达 + 免费机票抽奖猎手 + 行程福利。  
**不做**：实时报价 API、自动购票/报名、公网上线、绕过 robots。

---

## 二、当前状态

| 项 | 值 |
|---|---|
| 测试 | 347 passed + 样本 34/34 |
| 104 矩阵 | 64 PASS / 40 NOT_TESTED |
| Web | :8765 运行中 |
| Worker | daily_usage，间隔 1800s |
| 迁移 | 0009（含 0005→0009 兼容） |

---

## 三、最近修复（按时间）

| HEAD | 内容 |
|---|---|
| `d4b8e35` | R1-R5：ETag/304 链路、缓存首次写入、日期严格、失败退避 |
| `49afae7` | PC-01~05：外层冷却、ETag 头、缓存接入、改价更新、发布日严格 |
| `c258e9f` | 更新自检报告 HEAD |
| `3ade787` | P1 冷却/迁移/ETag |
| `87e2bee` | P1P2 全修 |
| `14d681e` | 冲刺收尾 P0-P5 |
| `5748b88` | Codex R1-R17 整改 |

---

## 四、最近审核链

1. **GPT-6 审核 `5d9c464`** → 发现 PC-01~07（冷却/ETag/缓存/改价/日期/A/B/版本）
2. **我修 `49afae7`** → GPT 复审仍有缺口
3. **GPT 复审 `49afae7`** → 发现 R1-R5（ETag 链路/缓存首次写入/日期/失败退避）
4. **我修 `d4b8e35`** → **待 GPT 复审**

---

## 五、核心教训（已写入 AGENTS.md）

1. **辅助测试通过 ≠ 主链路验证**——必须走 `run_discovery → FetcherRouter → Adapter → Cache → Parser → DB`
2. **不讨好用户**——如实说做了/没做/可能漏
3. **测试数量 ≠ 验收通过**——要说清测的是什么
4. **做完主动打包发 GPT**——不等催
5. **不自行宣布 V1.0/验收通过**

---

## 六、下一步

1. **交 GPT 复审 `d4b8e35`**（审核包：`review_exports/FlightHunter-PreCodex-Review-r1r5.zip`）
2. 按 GPT 意见继续修剩余问题
3. 等 GPT 确认后交 Codex 独立验收
4. **不新增来源/功能**，专注把已写的代码接成生效的业务流程

---

## 七、关键文件

| 文件 | 说明 |
|---|---|
| `docs/PRE_CODEX_SELF_AUDIT.md` | 自检报告 |
| `docs/REQUIREMENTS_MATRIX.md` | 104 矩阵 |
| `docs/PERSONAL_BETA_CHECKLIST.md` | 测试版清单 |
| `docs/CODEX_SPRINT_CLOSEOUT_HANDOFF.md` | 任务书 |
| `AGENTS.md` | 严谨性规则（已更新） |

---

## 八、当前测试命令

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe -B -m pytest tests/unit -q
.\.venv\Scripts\python.exe -B scripts/label_samples.py
.\.venv\Scripts\python.exe -B scripts/pack_gpt6_review.py
```
