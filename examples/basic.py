"""Crawl through ProxyHat residential proxies with Crawl4AI.

pip install "crawl4ai-proxyhat[crawl4ai]"
export PROXYHAT_API_KEY=ph_your_api_key
python examples/basic.py
"""

import asyncio
import os

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

from crawl4ai_proxyhat import ProxyHatRotationStrategy


async def main() -> None:
    # An API key auto-selects an active residential sub-user (or set
    # PROXYHAT_USERNAME / PROXYHAT_PASSWORD for explicit gateway credentials).
    strategy = ProxyHatRotationStrategy.from_credentials(
        api_key=os.environ.get("PROXYHAT_API_KEY"),
        country="us",
    )

    # Rotating: a fresh residential IP per request.
    rotating = CrawlerRunConfig(proxy_rotation_strategy=strategy)

    # Sticky: pin one IP for a logical session (30 minutes here).
    sticky = CrawlerRunConfig(
        proxy_rotation_strategy=strategy,
        proxy_session_id="demo-session",
        proxy_session_ttl=1800,
    )

    async with AsyncWebCrawler() as crawler:
        print("== rotating (fresh IP each request) ==")
        for _ in range(2):
            result = await crawler.arun("https://httpbin.org/ip", config=rotating)
            print(result.html)

        print("== sticky (same IP) ==")
        for _ in range(2):
            result = await crawler.arun("https://httpbin.org/ip", config=sticky)
            print(result.html)


if __name__ == "__main__":
    asyncio.run(main())
