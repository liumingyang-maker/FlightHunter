# FlightHunter V1.0 主业务冲刺 · 最终报告

**日期：** 2026-10-29  
**分支：** `develop`  
**基线起点（任务包）：** `f7bd865`  
**本报告 HEAD：** `f7bd865fae93baa3a9c80ad6a50dc76969f68dd0`  
**审核 ZIP：** `{{ZIP_PATH}}`

---

## 1. 真实完成的能力

### 监控与通知
- 到期扫描接入发现引擎；dry/execute 幂等分离；来源冷却；公平到期选取
- 站内通知 + Windows Toast 尝试；`recorded` / `toast_delivered` 语义分离
- `GET /api/v1/ops/status` 健康与任务统计
- `worker` / `scan-due` / 任务计划安装脚本

### 三引擎（有运行证据）
- **机票情报：** 已对公开列表页做**真实只读抓取**，写入 RawCandidate + **FareDealSignal（20+ 条）**；风险分层、愿望单匹配、提醒链路可用
- **行程福利：** 行程 CRUD、国家/城市/日期匹配、公开券 wallet.saved、中文指南生成、重匹配不清领取记录
- **抽奖报名：** 资格三态；本地 **Chromium 模拟站** 完成 预填→授权提交→回执→SQLite→通知；二次运行幂等；非 demo 活动 mock 回执隔离

### 用户可操作
- Web：首页 / 报名中心（含回执脱敏）/ 行程 / 机票雷达 / 卡包 / 提醒 / 设置（鉴权）
- CLI：`doctor` `seed` `discover` `scan-due` `worker` `demo-browser-e2e` `reconcile-stuck`

---

## 2. 明确未完成 / blocked

| 项 | 原因 |
|---|---|
| 真实外站自动提交 | **关闭**（安全门槛） |
| 实时双人可购票价 | 无授权供应商 → 情报模式 |
| 邮箱中奖实机 | 需用户 IMAP/OAuth；已有配置位与 .eml 扫描 |
| 手机推送送达 | 未接第三方推送 |
| 114/104 逐项全绿 | 见 `docs/REQUIREMENTS_MATRIX.md`，**不宣称 100%** |

---

## 3. 实机运行证据（本机 Windows）

```
# Chromium 模拟报名
uv run python -m app.cli demo-browser-e2e --submit
→ status=confirmed, receipt=DEMO-…, exit 0
→ SQLite Receipt.verified=True, Notification entry_confirmed
→ 二次运行 ALREADY_CONFIRMED 幂等

# 公开来源只读抓取（fare 列表页）
run_discovery(fare, dry_run=False, limit=1)
→ status=ok, signals_persisted=20
→ FareDeal ~22, FareDealSignal ~22

# UI
GET /entries/attempts → confirmed + 脱敏回执
GET /entries /notifications → 200
```

---

## 4. 测试

- **pytest：** 见最终审核包 `reports/pytest.txt`（目标 ≥166）
- **ruff：** exit 0
- 不等于 104 项验收全过

---

## 5. 安全

- 无自动真实支付/出票/过验证码
- 模拟回执不写非 demo confirmed
- 券码加密；导出无明文
- 不可信外链浏览器自动提交保持关闭

---

## 6. Git

- 连续 commit 于 `develop`，未 force push main
- 任务包例外：本批**一次**导出审核 ZIP

---

## 7. 建议后续

1. 用户本机再跑一次 `demo-browser-e2e --submit` 并打开 `/entries` 确认
2. 配置真实票价 Key / IMAP 后打开对应 blocked 能力
3. 按矩阵继续把 partial 升 done（真实来源与供应商）


