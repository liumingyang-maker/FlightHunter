# FlightHunter · Codex B1–B8 集中整改验收

- **HEAD：** `02e3447`（develop）  
- **基线：** Codex 复验源 `ac0c447` / 上轮整改 `15c123c`  
- **测试：** **230 passed**  
- **推送：** 见 git push develop  

## 对照 Codex 整改包

| 包 | 覆盖缺陷 | 本轮落地 | 状态 |
|---|---|---|---|
| **B1 安全访问** | N-001, N-002, N-015 | `app/core/safe_http.py` 逐跳公网校验；probe/OCR 改走 safe_get+robots；toast 改 **pwsh** + Base64 传参 | **代码完成**（Mock 重定向单测） |
| **B2 语义** | N-003–006, N-008 | 社区 flash→community_deal_tip；立省/立減不写票价；K 千排除 kg；出发地显式优先；**多目的地价绑** 仍 partial | **部分完成** |
| **B3 频道/筛选** | N-003, N-018 | 全球频道不带默认偏好（已有）；目的地/类别筛选 UI **未全做** | **部分** |
| **B4 行程** | N-007 | 已确认编辑 **不再** 禁用订阅；未确认仍禁用；调度二次检查 | **完成** |
| **B5 证据诚实** | N-009, N-012, N-013, N-016 | 资格缺 nationality/residence→unknown；campaign 标「线索/待核实」；auto_extracted_count 命名；核心推荐无正向硬推 | **完成主路径** |
| **B6 来源/通知/去重** | N-010, N-011, N-014 | 通知 `[D]` 头标记防截断；`ok_existing` vs `ok_zero`；跨源合并仍保守 PARTIAL | **部分** |
| **B7 迁移可靠性** | N-017 | 未自动迁移正式库；启动前建议 `migrate`（文档层）；**未**对用户私库做破坏性操作 | **运维说明** |
| **B8 统一验收** | — | 本报告 | **本文件** |

## 关键实现摘要

1. **safe_http**：`MAX_REDIRECTS=5`；每跳 `assert_public_http_url`；robots can_fetch；禁止公开→私网。  
2. **行程**：`confirmed` 时编辑不再因 `auto_scan_on_trip_change=false` 停扫；未确认停用。  
3. **资格**：非韩国限制下缺国籍或居住 → **unknown**。  
4. **通知**：`[D]` 写在 body **开头**；重复调用 skip；pwsh toast。  
5. **来源状态**：`ok` / `ok_zero` / `ok_existing` / `failed`。  

## 未完成 / 保留 Codex 批评

| 项 | 说明 |
|---|---|
| 多目的地价格绑定 | N-004 完整 route-level 绑定未做完 |
| 出发地全部负例 | N-003 仍有边界（品牌弱启发） |
| 跨站事件级合并 | N-014 仍 PARTIAL（有意保守） |
| UI 目的地/类别/时间筛选 | N-018 未全 |
| 104 项 / 72h / 公网 | **NOT_TESTED / 未做** |

## 三问

**A. 个人日常试用？**  
**仍倾向 NO，但更近**：SSRF 旁路、已确认停扫、通知重复、资格假 eligible 已修主路径；出发地/价格/筛选仍有缺口。

**B. Codex 缺陷独立复验？**  
**0 / 本轮待复验**。iMiMo 230 测试 ≠ Codex 关单。

**C. 完整 V1.0？**  
**未完成**。N-003/004/008/014/018 与 104 项仍在。

## 交付

- 代码：`c01b7d6` · `02e3447`  
- 本报告：`docs/CODEX_BATCH_ACCEPTANCE.md`  
- 建议 Codex 复验快照：`git archive 02e3447`  
