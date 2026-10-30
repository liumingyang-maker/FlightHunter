# FlightHunter · Codex 缺陷整改报告（iMiMo）

- **修复 HEAD：** `15c123c`（相对 Codex 审计源 `603bb48`）  
- **测试：** **228 passed**  
- **原则：** 安全与业务触发优先；不新增来源；不宣称完整 V1.0  

## 对 GPT 整改方案的取舍

| 采纳 | 调整/不采纳的部分 |
|---|---|
| D-001/D-002 优先安全与确认门槛 | 同意，先修 |
| D-003~D-007 情报语义 | 同意；实现上用启发式+unknown，不引入重型 NLP |
| D-008 事件级合并 | **部分采纳**：增强标题归一；完整跨站实体 ID 仍 partial（避免误合并） |
| D-009 通知幂等 | 采纳：已外送不再 console/toast |
| D-010 核心推荐 | 采纳：未知出发地 `core_recommend=false` |
| D-011 ok_zero | 采纳：业务 status 区分 |
| D-012 HKG→HKG | 采纳：目的抽取排除出发语境香港 |
| 不要求本轮完成公网渗透/CSP 全套 | 保留为后续；本轮 XSS 用文本转义+URL 白名单 |
| 不重置 72h 观测 | 遵守 |

## 缺陷核对与修复

| ID | 原 Codex | 当前 | 修复位置 | 测试 |
|---|---|---|---|---|
| D-001 | P1 未确认可编辑后扫描 | **已修** | `trips/service.py` update；`jobs.py` claim 再查 confirmed/demo | `test_codex_remediation.py` |
| D-002 | P1 innerHTML XSS | **已修** | `fare.html` esc + safeHttpUrl | 手工/静态；浏览器全量 exploit 未做 |
| D-003 | P1 出发地误判 | **已修** | `intel.extract_origin_*` 航司剥离/显式出发优先 | D-003 单测 |
| D-004 | P1 全球错价被过滤 | **已修** | UI 全球频道不发 origins；空偏好不过滤 | D-004 单测 |
| D-005 | P1 减免当票价 | **已修** | 解析最高減/立減不写 reported_total | D-005 单测 |
| D-006 | P2 20KG→20000 | **已修** | K 千正则排除 kg | D-006 单测 |
| D-007 | P1 发布时间 | **部分** | FlyNext 列表标签日期写入 published_at；UI 区分发布/发现 | 通用 HTML 仍 partial |
| D-008 | P1 去重 | **部分** | 标题归一加强；跨源改写仍可能分裂 | — |
| D-009 | P2 通知重复外送 | **已修** | 已 delivery 跳过 | delivery 逻辑 |
| D-010 | P2 核心推荐 | **已修** | unknown 不 core_recommend | — |
| D-011 | P2 ok vs ok_zero | **已修** | fetch_source business status | 含 ok_zero 测试 |
| D-012 | P2 HKG→HKG | **已修** | dest 排除出发语境香港 | extract 测试 |

## 未能在本机完成/需 Codex 复验

1. 浏览器 XSS 利用链完整验证（只做了代码层修复）  
2. FlyNext 真实四条再抓全链路（依赖外网时点）  
3. 通知真实桌面 toast 第二次不响  
4. 历史错误 enabled 订阅的批量修复脚本（调度已跳过；未删库）  

## 提交

`15c123c` fix(codex): D-001~D-012…  

**不宣称** 12/12 已由 Codex 关单；等待独立复验。
