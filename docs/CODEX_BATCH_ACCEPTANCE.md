# FlightHunter · 合并 Codex 实施修复（bca4a4f）验收

- **日期：** 2026-10-31  
- **基线：** `58eed2b` → cherry-pick `bca4a4f` → **`4f89013`**（develop）  
- **来源：** `docs/CODEX_IMPLEMENTATION_AUDIT_20261030.md` + worktree `codex-fixes`  
- **方式：** 审阅 diff 后 cherry-pick，**非**整目录覆盖  

## 本批采纳（Codex 实施）

| 项 | 落地 | 状态 |
|---|---|---|
| `PublicAddressBackend` 连接期 DNS 绑定 | `safe_get` + HTML/RSS 适配器；SNI/Host 仍用域名 | **采纳**（httpx 内部 API，已标兼容风险） |
| `not ip.is_global` | 共享地址 `100.64.0.0/10` 等拒绝 | **采纳** |
| 流式读 HTML/robots | 超限即停 | **采纳** |
| 品牌≠出发地 | 移除 Cathay/HK Express → HKG 弱提示 | **采纳**（更诚实） |
| 多金额不写统一票价 | 含 ¥/元/千元写法 | **采纳** |
| 发布标签双路径 | 常规 + `/blog/` 回退 | **采纳** |
| travel 筛选接 FareDeal 窗口 | 显式 `travel` 区间重叠 | **采纳** |
| 未知自动化许可 → MANUAL_ONLY | 仅 `allowed` 才可预填 | **采纳** |
| 年龄不假定 18 | 无官方规则 → unknown | **采纳** |
| 旧库不被 create_all 改写 | 仅新库 `init_db` | **采纳** |

## 本机验证（合并后主仓）

| 检查 | 结果 |
|---|---|
| `pytest tests/unit` | **279 passed，1 warning** |
| `ruff check`（改动文件） | All checks passed |
| R-001~R-017 自查 | **18/18 PASS** |
| 新库 create_all | action=create_all_new_db |
| 旧库（仅 legacy 表）启动模拟 | **表清单未变**，无 trips |
| 0001 vs head | outdated, ok=false |
| PublicAddressBackend | 已挂接；Unix socket 拒绝 |
| 100.64.0.1 / 10.0.0.1 | blocked |

## 仍 partial / NOT_TESTED（沿 Codex 报告）

| 项 | 说明 |
|---|---|
| 浏览器子资源 / 重定向 | 未绑 PublicAddressBackend |
| HTTPX 私有 `_network_backend` | 升级需重跑集成 |
| 抽奖中国出境正向核心 | 产品/模型未闭环 |
| 通知精确一次 / 真实 toast | 需桌面与进程中断实测 |
| 104 项 / 72h / 公网 | **NOT_TESTED** |

## 三问

**A. 个人日常试用？**  
**更近，仍非关单**。安全连接绑定、旧库静默改表、年龄假定等硬伤已修。

**B. Codex 独立复验？**  
**0**。279 ≠ 关单。

**C. 完整 V1.0？**  
**未完成**。104 项、72h、真实 toast、公网仍开。

## 交付

- 合并提交：`4f89013` fix: harden flight intelligence and source safety  
- Codex 原报告：`docs/CODEX_IMPLEMENTATION_AUDIT_20261030.md`  
- 冒烟：`scripts/smoke_after_codex_merge.py`  
- 建议复验基线：`git archive 4f89013`  

**不宣称** V1.0 / 公网安全认证 / Codex 关单。
