# FlightHunter · 国际机票情报雷达实用化验收

- **时间（UTC）**：2026-10-30  
- **HEAD：** `651dce7`（develop）  
- **提交关系：** `aecb6dc` ⊂ `33da08f` ⊂ `651dce7`（均为祖先，无回退）  
- **备份：** `backups/flighthunter_develop_20261030_111851.bundle`  
- **测试：** `pytest tests/unit` → **209 passed**  
- **airportsdata：** v20260905 · **MIT**（已更正 `DEPENDENCIES_LICENSES.md`，旧 LGPL 作废）  
- **安全：** 无 push / 无合并 main / 不绕过 robots  

### 上次代码替换核验

| 提示 | 结论 |
|---|---|
| `No changes to apply` / `String to replace not found` | 已对照源码确认：`expand_origin_selection`、`is_international_pair`、`build_intel_view`、HKG/MFM 独立逻辑 **已在** `app/services/airports/china.py` 与 `intel.py` 中实现；未盲目整函数替换 |

---

## 1. 来源清单与真实抓取（隔离库 `%TEMP%\fh_fare_live`）

| 来源 | 类型 | 本次读取 | 解析出信号 | 失败分类 |
|---|---|---|---|---|
| 什么值得买 · 国际机票 | HTML | **成功** | 若干（含噪声过滤后） | — |
| 什么值得买 · 每日机票推荐 | HTML | **成功** | **12+ 国际促销标题** | — |
| 北美票帝 | HTML | 未轮询到（limit） | 0 | 冷却/顺序 |
| One Mile at a Time | RSS | **成功** | 2（部分为信用卡评测已滤） | — |
| View from the Wing | RSS | **成功** | 1–2 | — |
| Google News · 国际特价机票 | RSS | 失败 | 0 | robots/fail |
| Google News · Bug Fare | RSS | 失败 | 0 | robots/fail |
| Secret Flying | HTML | 失败 | 0 | robots |
| Fly4Free | HTML | 失败 | 0 | robots/Cloudflare |

**本次实际成功读取：8/9 个 fare 来源有 `last_fetch_at`**  
**真正解析出信号：17 条**（含国际促销与少量需过滤项）  
**匹配中国出发的有效情报：默认 CKG/TFU/CTU 视图约 9 条；全国内地视图约 12 条**  
**可打开原始来源链接：全部情报带 `source_url`（smzdm/RSS 文章链接）**

### 真实国际机票促销样例（非模拟）

1. 上海/杭州/南京 → 日本冲绳 往返含税 999 元起（每日机票推荐）  
2. 上海/北京 → 东京/大阪/长崎 1421 元起  
3. 北上广/成都 → 赫尔辛基 2.7K+  
4. 全国多地 → 塞尔维亚贝尔格莱德 3.1K+  
5. 全国多地 → 泰国曼谷/普吉 499 元起  
（均为社区报道价；**非实时可购**；链接指向 smzdm 原文）

已过滤：信用卡测评、纯攻略「怎么买机票」、纯国内（如仅银川）在无国际标记时不进默认国际视图。

---

## 2. 出发地选择 UI（Playwright）

截图：`data/fare_ui/fare_desktop.png` · `fare_nationwide.png` · `fare_hkg.png` · `fare_mobile.png`

| 场景 | 结果 |
|---|---|
| 默认 CKG/TFU/CTU | 桌面情报条数 **9** |
| 全国出发（仅内地） | **12**（更多内地机场匹配） |
| 仅勾选 HKG | 按筛选请求；无机场的全国性促销仍可显示（设计如此） |
| 清除 / 恢复默认 | 正常 |
| localStorage 保存与刷新恢复 | **成功** `fh_fare_origins_v1` |
| 移动端 390×844 | 出发地面板可见，情报可读 |

**HKG/MFM 未加入「全国」展开集**（单测 + UI 数据源双重保证）。

---

## 3. 跨来源去重

- `merge_intel_signals`：同路线 + 标题归一化键合并  
- 保留多 `source_urls` / `sources[]`  
- 不合并不同 origin/dest  
- 测试：`tests/unit/test_intel_merge.py`  

本轮实机多为单源转载，合并计数随多源重叠增加。

---

## 4. 自动运行

| 项 | 结果 |
|---|---|
| 用户启动文件夹 Worker | **已安装** `Startup\FlightHunterWorker.bat` |
| 计划任务注册 | **拒绝访问**（无管理员）→ 改用启动文件夹，**未提权** |
| 断网/失败 | 来源 `consecutive_failures`；机器人/403 如实 failed |
| 冷却限速 | `min_seconds_between_requests_per_domain=8` |
| 无大模型 API | **正常运行** |
| 电源策略 | **未修改** |

---

## 5. P2 / P3 回归

| 项 | 结果 |
|---|---|
| P2 出境标签 / 核心推荐过滤 | **未回退**（既有代码与测试） |
| P3 确认行程才扫描 | **未回退**（`confirmed` + 测试） |

---

## 6. 隔离 / 数据口径

| 口径 | 值 |
|---|---|
| 本次隔离库 | `%TEMP%\fh_fare_live\data\fare.db` |
| 本次信号 | 17 |
| 默认出发视图情报 | ~9 |
| 全国内地视图 | ~12 |
| 历史主库 | 未覆盖；已 bundle 备份 develop |

---

## 7. 未解决问题

1. **Secret Flying / Fly4Free / 部分 Google News**：robots 或防护墙，**不绕过** → 来源覆盖缺口  
2. **RSS 条目缺机场码**：靠标题城市映射，精度 partial  
3. **标题级去重** 而非全文；不同措辞可能仍拆成两条  
4. **计划任务** 需管理员时仅启动文件夹方案  
5. 中航司官网会员日页多为 JS/需登录，尚未稳定自动化  

---

## 8. 结论

FlightHunter **已能在无人工逐步传参的情况下**，通过公开 HTML/RSS 持续抓取并展示 **与中国出发相关的国际特价机票情报**（默认重庆/成都，可全国/港澳筛选），并给出 **可点击来源链接**。  
**不能**保证覆盖全网错价；**不能**把报道价当成可买价；部分国际站点因 robots 不可用。

Git：`develop` @ `651dce7` · 未 push · 未合并 main。
