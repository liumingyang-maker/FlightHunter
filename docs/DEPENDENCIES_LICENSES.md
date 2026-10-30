# 依赖与开源许可（P1 相关新增）

| 包 | 用途 | 许可（PyPI 常见） |
|---|---|---|
| airportsdata | 机场/IATA 数据 | LGPL-3.0 |
| pytesseract | OCR | Apache-2.0 |
| pillow | 图像 | MIT-CMU |
| httpx | 抓取 | BSD-3 |
| fastapi/uvicorn/sqlalchemy | 应用栈 | MIT/Apache/BSD |

已研究未默认引入运行时依赖：RSSHub、changedetection.io（独立服务成本高）、trafilatura、apprise（通知可选后续）。
walkabout：评估后未作为硬依赖。

**说明：** 实时报价供应商适配器代码保留，V1.0 不强制接入。
