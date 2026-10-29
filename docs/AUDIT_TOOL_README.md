# FlightHunter 一键导出审查包（Windows 11）

**用法：** 把本压缩包中的 `tools/export_review_bundle.py` 和 `生成GPT审核包.cmd` 放进 FlightHunter Git 仓库**根目录**（与 `app/`、`docs/` 同级）。这只是一个导出工具，不会调用 GPT API、Codex，也不会向网络上传文件。

1. 让 MiMo 完成修改并提交代码。最好推送 `develop`，确保 HEAD 对应远端。
2. 第一次想比较 `805ed36 → 78c23bd` 时，在仓库根目录运行：
   ```powershell
   py -3 tools/export_review_bundle.py --base 805ed36
   ```
   或者双击 `生成GPT审核包.cmd`，它会默认使用上一次导出 SHA（首次为 HEAD~1）。
3. 工具会执行 `python -m pytest -q` 和 `ruff check .`，产生 `review_exports/FlightHunter-review-<SHA>.zip`。如果缺依赖或测试失败，日志会如实记录，不会冒充通过。
4. 上传这个 ZIP 到目前的 ChatGPT 聊天，并说“差分审核”。我可以基于**完整源码 + 增量 diff + 测试日志 + SHA** 独立审查。
5. 下一次双击脚本，默认自动以上次导出的 SHA 为比较起点（若重复导出同一 SHA，会回退到前一个提交）。**注意“上次导出”不代表“上次审核通过”**；如需精确复审，请用 `--base <上次审核过的SHA>` 显式指定。

也可以直接：
```powershell
py -3 tools/export_review_bundle.py --base 805ed36
py -3 tools/export_review_bundle.py --skip-tests
```

**注意安全：** 只导出已经 Git 跟踪的文件，但如果密钥已经错误地提交进 Git，它仍可能出现在源码中。工具会拦截部分敏感文件名，但无法保证不会泄露个人信息。上传前检查 ZIP；`review_exports/` 应加入 `.gitignore`，避免意外提交。

**重要限制：** 这是“上传一个 ZIP 即可审核”的半自动方案。当前普通 ChatGPT 聊天不能被 MiMo 客户端自动唤醒，也不能被用户本地脚本直接推送附件，不能声称已经实现完全无人值守协作。
