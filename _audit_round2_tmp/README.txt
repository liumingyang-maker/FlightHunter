# FlightHunter 第二轮差分审核交付包

基准 SHA: 805ed36ba8a28abad72314a6dc3a1b35acf5e286
目标 SHA: a49fecfec08ccbd2359c3206c73695d340af614f

内容:
- 审核报告 MD：对应 docs/REVIEW_FOR_GPT.md 第10节。
- 机器修复任务 JSON：包含四项 P0、五项 P1、三项 P2，以及 I1–I12 状态。
- audit_repros.py：离线隔离测试的简化复现脚本（需要 FlightHunter Python 环境，且须从项目根目录调用，不做网络访问）。

请 MiMo 先补真实失败回归测试后修复 P0，然后处理 P1。严禁以 mock/partial 代替实际完成；GitHub PR 不得自动合并 main。

运行复现建议：将 audit_repros.py 放在仓库外的临时目录；在 FlightHunter 项目根目录执行 `PYTHONPATH=. python <脚本路径>`（Windows 使用 `set PYTHONPATH=.` 或 `$env:PYTHONPATH='.'`）。
