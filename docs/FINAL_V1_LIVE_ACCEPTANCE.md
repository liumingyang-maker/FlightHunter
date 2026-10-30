# FlightHunter V1.0 真实业务验收（产品方向重构后）

- **时间：** 2026-10-30  
- **HEAD：** `aecb6dc`（develop）  
- **测试：** `pytest tests/unit` → **207 passed**  
- **原则：** 情报模式；无实时报价供应商；不自动购票/报名  

---

## 1. 产品基线

见 `docs/PRODUCT_BASELINE_20261030.md`。  
**需求调整：** 实时机票报价 API **不再** 为 V1.0 强制项；历史 `quote_provider` 代码保留，默认关闭。

---

## 2. P1 国际特价机票情报雷达

| 验收项 | 结果 | 证据 |
|---|---|---|
| 重庆+成都多选匹配 | **实现** | `IntelFilter(preferred_origins=["CKG","TFU","CTU"])` · `airportsdata` |
| 全国=仅内地，不含 HKG/MFM | **实现** | `expand_origin_selection(china_mainland_all=True)` → 256 内地机场，无 HKG/MFM |
| 额外勾选 HKG/MFM | **实现** | `include_hkg/include_mfm` |
| 纯国内票排除 | **实现** | `is_international_pair(CKG,SHA)=False` → 过滤 |
| 情报分类 | **实现** | bug/fuel/hidden/mileage/flash/community |
| 多源去重保留来源链 | partial | Deal 级 dedup_key；跨源标题合并未完全 |
| 过期不进当前有效 | **实现** | `hide_expired` + 标题「过期」 |
| 无 API 仍可用 | **实现** | `GET /api/v1/fare/intel` · `build_intel_view` 不依赖报价 |
| 真实抓取 | **partial** | 隔离库 discover：smzdm 成功写入信号；SecretFlying **robots 拒绝**；部分列表 0 解析 |
| Bug 票独立分类 | **实现** | `suspected_bug_fare` + 风险说明 |

**实机样例：** 隔离扫描写入至少 1 条含来源 URL 的国际机票情报信号；无编造「历史最低可购」。

**未完成：** 全国出发 UI 多选控件（API 已支持 origins 参数）；跨站全文去重；Secret Flying 合规接入待评估（robots）。

---

## 3. P2 免费国际机票抽奖

| 验收项 | 结果 |
|---|---|
| 全球发现/溯源/OCR 继续可用 | **保留**（既有 unattended 管道） |
| 纯国内/汽车/现金不进核心推荐 | **实现** `china_outbound_relevance=not_travel_ticket` |
| 国际机票但内地出发未知 | **待核实** `unknown_origin_pending` |
| LOCAL AIRPORT FOOD 回归 | **仍 open**（见 KOREA 报告） |
| 日期/资格未知不误标结束 | **保留** pending/open/closed 模型 |

---

## 4. P3 Trip Benefits（确认行程后）

| 验收项 | 结果 |
|---|---|
| 未确认行程不启动正式扫描 | **实现** `confirmed=False` → 不注册订阅 |
| demo 不触发正式监控 | **保留** |
| 确认后启动 | **实现** `confirmed=True` 或 `confirm-trip` CLI |
| 取消停扫归档 | **实现** `cancel_trip_scans` |
| 无真实领取不显示已领取 | **保留** |

**测试：** `tests/unit/test_p3_trip_confirm.py`

---

## 5. 持续运行 / 无 AI / 安全

| 项 | 结果 |
|---|---|
| 无付费大模型启动 | **是**（AI config 默认关） |
| Worker 调度 | **保留**（含 raffle 主流程开关） |
| 测试隔离鉴权 | **保留** state_dir |
| 自动购票/付款/未授权报名 | **禁止** |

---

## 6. 依赖与许可

见 `docs/DEPENDENCIES_LICENSES.md`（airportsdata=**LGPL-3.0**，引入需随包分发源码义务已注意；仅本地数据查询）。

---

## 7. 三问（真实能力）

### 1）能否稳定帮用户发现国际机票促销情报？

**能以「情报助手」方式稳定运行，不能承诺实时全网错价秒推。**  
已具备：默认 CKG/TFU/CTU、全国内地、HKG/MFM 可选、国际航线过滤、分类、来源链接、过期过滤、无报价 API。  
实机：公开社区源可抓到信号；部分源 robots 失败已如实记录。用户需点击来源自行查价购买。

### 2）免费抽奖与行程福利是否按新范围运行？

**是。**  
抽奖继续全球发现 + 中国出境标签/核心推荐过滤；LOCAL AIRPORT FOOD 回归有效。  
行程福利仅在 **用户确认真实行程** 后扫描；demo 不触发；取消停扫。

### 3）阻止 V1.0 日常使用的真实问题？

1. **情报源覆盖有限**：部分国际源 robots/403；中文源结构变化会导致 0 解析。  
2. **UI 出发地多选** 尚未做成完整前端控件（API 已通）。  
3. **跨站同一促销去重** 仍 partial。  
4. **P2** 适合内地出境的「当前可报名免费机票」仍稀少/多为待核实。  
5. **P3** 需用户真实确认行程后才有价值；无确认则无福利输出（符合设计）。  
6. **未注册** Windows 开机自启任务（可用 `scripts/install_worker_task.ps1`，需用户策略）。

---

## 8. Git

`develop` @ `aecb6dc` · 未 push · 未合并 main。  
备份：Git 历史 + 本报告；无破坏性 DB 迁移（0003 仅新增 `trips.confirmed`，可降级）。
