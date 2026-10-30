# 技术债清单

## 高

1. **HTTPX 私有 `_network_backend` 挂接**（`app/core/safe_http.py`）
   - `public_http_transport()` 依赖 httpx 内部结构；升级 `httpx`/`httpcore` 可能失效
   - 升级 checklist：跑 `tests/unit/test_codex_independent_regressions.py` + 真实 HTTPS 抽检
   - 依赖已钉：`httpcore>=1.0.0,<2.0.0`

2. **Playwright 网络栈无公网 IP 绑定**
   - `app/core/browser_safety.py` 仅做启动前 DNS+公网校验 + route 拦截
   - 无法像 `PublicAddressBackend` 那样「只连已验证 IP」
   - 风险：DNS 重绑定在浏览器内仍可能；仅允许 `automation_policy=allowed` 站点

3. **通知 exactly-once 未证明**
   - 进程在外送与事务提交之间崩溃的语义：at-most-once + 失败上限（3）
   - 需真实桌面 toast / 中断实验

## 中

4. 跨站转载事件级合并仍保守（防误合并）
5. 抽奖「中国内地出境」正向核心推荐未闭环（需产品/数据模型）
6. 旅行日期依赖 `FareDeal.travel_window_*`；多数来源无结构化出行日

## 低

7. 部分历史 LIVE_* 文档数字是当时快照
8. `_first_live_test/` 脚本未纳入统一 CLI