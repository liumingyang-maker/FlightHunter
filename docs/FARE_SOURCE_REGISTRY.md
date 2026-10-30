# FlightHunter 机票情报来源注册表

**更新：** 2026-10-30 · daily_usage 库 `sources` · module=fare  

| 名称 | 区域 | 模式 | 状态启发 | 备注 |
|---|---|---|---|---|
| 什么值得买 · 国际机票 | 中国内地 | httpx | active · 常有价值 | 中国出发主力 |
| 什么值得买 · 每日机票推荐 | 中国内地 | httpx | active · 高价值 | 全国多城促销 |
| 北美票帝 | 中国相关 | httpx | active | 错价案例 |
| Secret Flying | 全球 | httpx | 常 robots 失败 | 错价/优惠 |
| Fly4Free | 全球 | httpx | Cloudflare/robots | 受限 |
| One Mile at a Time | 全球 | rss | active | 航司促销 |
| View from the Wing | 全球 | rss | active | 航司促销 |
| Google News · 国际特价机票 | 中国 | rss | 常失败 | 新闻 |
| Google News · Bug Fare | 全球 | rss | 常失败 | 错价新闻 |
| MainlyMiles | 亚洲 | httpx | observation | 新 |
| SingPromos Airlines | 新加坡 | httpx | observation | 新 |
| The Flight Deal | 全球 | httpx | candidate | 错价 |
| Travel-Dealz | 全球 | httpx | candidate | 特价 |
| Flyday.hk | 香港 | httpx | candidate | 港澳 |
| FlyNext.hk | 香港 | httpx | candidate | 港澳 |
| Google News · 香港机票优惠 | 香港 | rss | candidate | 港澳 |
| Google News · Error Fare | 全球 | rss | candidate | 错价 |

**统计口径：** `source-health` 分 historically_fetched / round_success / failed / cooldown / valuable。

**未接入说明：** 航司官网多为 JS/登录；changedetection/RSSHub/Apprise 未强制引入（现有 Worker+RSS 足够起步）。
