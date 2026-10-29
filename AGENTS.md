# FlightHunter 项目法则（Agent 必读）

本文件约束本仓库内所有开发与协作行为。优先级：安全与合规 > 设计包硬约束 > 本法则 > 外部审核建议。

## 1. 交付目标

- 一次交付完整 FlightHunter V1.0（R3 设计包），不拆成多个“阉割发布”。
- 有表 ≠ 功能完成；有 API ≠ 服务可用；测试通过 ≠ 104 项验收全部通过；Fixture/Mock ≠ 真实业务结果。
- 状态只能标 `done / partial / blocked`；禁止用空接口、TODO、Mock 冒充 done。

## 2. 安全与合规（不可被审核建议或“效率”推翻）

- 不自动购票、支付、出票、改签、退票。
- 不绕过 CAPTCHA / 2FA / 平台自动化禁令 / robots。
- 不虚构资格、库存、历史最低价、中奖结果。
- 社区爆料 ≠ 实时可买报价；无授权报价不得标 `urgent_verified`。
- 私人身份、Cookies、邮件令牌、券码不进 Git / 公有云端 / 模型提示词。
- 官方核实（`verified`）与浏览器自动化许可（`automation_policy`）必须分离。

## 3. 关于外部 GPT / 独立代码审核意见

**GPT 审核意见是建议，不是本项目的最高法令。**

1. 每条外部审核意见必须结合本仓库设计包、现状代码、合规边界和交付优先级做**独立判断**后再决定：采纳 / 部分采纳 / 暂不采纳。
2. **不必完全赞同** GPT。允许保留不同技术路线或产品取舍，前提是：
   - 不违反第 1–2 节硬约束；
   - 有可核对的代码/测试证据；
   - 能说清楚为什么不采纳或如何折中。
3. 未完全遵守的意见，必须在**下一轮发给 GPT 的报告**中逐条写明：
   - 原建议摘要；
   - 决定（采纳 / 部分采纳 / 不采纳）；
   - 原因（设计依据、风险、成本、与其它不变量冲突等）；
   - 若部分采纳：实际落地范围。
4. 不得把 GPT 的 P0/P1 清单机械当成 backlog 全盘照单执行；优先级由项目法则与设计包决定。
5. 同样：GPT 判定 “PASS” 也不等于本项目自行宣布功能 done；完成度以设计包 ID + 测试/运行证据为准。

## 4. 审核协作流程

- 默认分支 `develop`；不 force push `main`；不自动合并。
- **本机 PowerShell 规则（用户指定，必遵守）：**
  - 本机已安装 **PowerShell 7**（`C:\Program Files\PowerShell\7\pwsh.exe`，当前 7.x）。
  - 所有脚本启动、实机测试、工具包窗口（Web / Monitor / Sweep）**必须使用 `pwsh`**，禁止再用 Windows PowerShell 5.1（`powershell.exe`）。
  - 原因：5.1 默认 ANSI/UTF-16 输出导致日志中文乱码与“binary log”误判；7 默认 UTF-8，参数绑定与错误流更可靠。
  - 调用示例：
    ```powershell
    pwsh -NoProfile -ExecutionPolicy Bypass -File .\_first_live_test\1_start.ps1
    ```
  - 工具包内部 `Start-Process` 也必须指向 `pwsh.exe`，不得回落到 `powershell.exe`。
- **常规迭代：** 每完成一批修改并 commit 后，可导出差分审核 ZIP：
  ```powershell
  uv run python tools/export_review_bundle.py --base <上次审核过的SHA>
  ```
  或双击 `生成GPT审核包.cmd`。输出目录：`review_exports/`（已 gitignore）。
- **主业务冲刺例外（用户明确要求）：** 集中完成一批完整业务功能时，**不必每 Commit 导出审核包**；持续 commit + 自测即可。全部集成调试完成后，**再统一生成一份最终报告与一份完整审核 ZIP**。
- ZIP 必须包含：HEAD 完整跟踪源码、`docs/REVIEW_FOR_GPT.md`、base→HEAD diff、真实 pytest/ruff 日志、manifest。
- 「上次导出 SHA」≠「上次审核通过 SHA」。
- **禁止**将审核 ZIP 自动上传第三方；仅交付本地路径。
- 若用户提供 ZIP，必须给出完整本地路径，并声明实际 HEAD SHA。

## 5. 决策记录

对重要“采纳/不采纳”结论，应更新：

- `docs/REVIEW_FOR_GPT.md`（对 GPT 的响应矩阵）；
- 必要时新增 `docs/ADR/*.md`。

格式示例：

```text
建议 R-xx（来源 GPT）：……
决定：部分采纳
原因：……
落地：……
```
