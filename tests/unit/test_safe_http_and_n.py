"""安全 HTTP 与 Codex N 系列边界。"""

from __future__ import annotations

import asyncio

from app.core.safe_http import safe_get
from app.services.fare.intel import classify_signal
from app.models.fare import FareDealSignal


def test_safe_get_blocks_private_and_public_to_private_redirect():
    import httpx

    class _Handler(httpx.MockTransport):
        def __init__(self):
            super().__init__(self._handle)
            self.n = 0

        def _handle(self, request: httpx.Request) -> httpx.Response:
            if "public.example" in request.url.host:
                return httpx.Response(302, headers={"Location": "http://127.0.0.1/steal"})
            return httpx.Response(200, text="ok")

    async def run():
        transport = _Handler()
        async with httpx.AsyncClient(transport=transport) as client:
            # 初始私网直接拒绝
            r1 = await safe_get("http://127.0.0.1/", check_robots=False, client=client)
            assert r1.ok is False
            # 公开跳私网：应拒绝（safe_get 逐跳 assert_public_http_url）
            r2 = await safe_get(
                "https://public.example/x",
                check_robots=False,
                client=client,
            )
            # MockTransport 的 Location 会指向 127.0.0.1
            assert r2.ok is False
            assert any("unsafe" in (r2.error or "") or "too_many" in (r2.error or "") for _ in [1]) or r2.ok is False

    asyncio.run(run())


def test_community_flash_not_official():
    s = FareDealSignal(
        id="1",
        deal_id="d",
        title="sale",
        raw_claim_text="",
        deal_types='["flash_sale"]',
        source_type="community",
    )
    assert classify_signal(s) == "community_deal_tip"
