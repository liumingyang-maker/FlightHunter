# FlightHunter 四频道机票情报设计

## 统一数据层

- **同一** SQLite 表：`fare_deal_signals` / `fare_deals`
- **同一** 来源注册：`sources.module=fare`
- **同一** 去重：`merge_intel_signals`（多源保留 `source_urls`）
- **同一** 通知与 Worker：`raffle_auto_pipeline` / fare discover

频道是 **视图路由**，不是四套采集。

## 频道定义

| 频道 | key | 规则 |
|---|---|---|
| 我的出发地 | `my_origin` | 主列表=`explicit_city`∩偏好机场；折叠区=全国/未知 |
| 全国出发 | `china_mainland` | 内地机场或全国线索；**排除**仅港澳机场 |
| 香港／澳门 | `hk_mo` | HKG/MFM 或标题含港澳线索 |
| 全球错价 | `global_error` | bug/error/mistake/fuel dump 类；不限出发地 |

同一 `signal_id` 可属多频道；通知按事件去重。

## API

`GET /api/v1/fare/intel?channel=my_origin|china_mainland|hk_mo|global_error`

## 适用性标注

- `explicit_city`：标题/解析含偏好机场  
- `national_multi_city_pending`：全国/多城，**不**等同含 CKG/TFU  
- `origin_unknown`：未知  

## 错价

需 `error_fare` 类型或标题 bug/error/fuel dump 证据；普通低价不进错价频道。
