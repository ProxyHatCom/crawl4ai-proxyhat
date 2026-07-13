# crawl4ai-proxyhat

Route [Crawl4AI](https://github.com/unclecode/crawl4ai) crawls through [ProxyHat](https://proxyhat.com?utm_source=github&utm_medium=readme&utm_campaign=crawl4ai) residential proxies — rotating IPs, geo-targeting, and sticky sessions mapped to Crawl4AI's own proxy rotation strategy.

[![CI](https://github.com/ProxyHatCom/crawl4ai-proxyhat/actions/workflows/ci.yml/badge.svg)](https://github.com/ProxyHatCom/crawl4ai-proxyhat/actions/workflows/ci.yml)
[![Compatible with Crawl4AI latest](https://github.com/ProxyHatCom/crawl4ai-proxyhat/actions/workflows/compat.yml/badge.svg)](https://github.com/ProxyHatCom/crawl4ai-proxyhat/actions/workflows/compat.yml)
[![PyPI](https://img.shields.io/pypi/v/crawl4ai-proxyhat)](https://pypi.org/project/crawl4ai-proxyhat/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Why

Crawling at scale from datacenter IPs gets you blocked and rate-limited. This package plugs ProxyHat's residential IPs (50M+ across 148+ countries) into Crawl4AI through its first-class `ProxyConfig` and `ProxyRotationStrategy` APIs — a fresh IP per browser context by default, and one pinned IP per Crawl4AI proxy session when you want it. No fork, no boilerplate.

## Install

```bash
pip install crawl4ai-proxyhat
```

Crawl4AI itself is an optional dependency — bring your own version (`crawl4ai>=0.5`), or install it alongside:

```bash
pip install "crawl4ai-proxyhat[crawl4ai]"
```

## Quick start

```python
import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai_proxyhat import ProxyHatRotationStrategy

async def main():
    # An API key auto-selects an active residential sub-user:
    strategy = ProxyHatRotationStrategy.from_credentials(
        api_key="ph_your_api_key",
        country="us",
    )
    run_config = CrawlerRunConfig(proxy_rotation_strategy=strategy)

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun("https://httpbin.org/ip", config=run_config)
        print(result.html)

asyncio.run(main())
```

Get an API key at [proxyhat.com](https://proxyhat.com?utm_source=github&utm_medium=readme&utm_campaign=crawl4ai).

Prefer a single fixed proxy? Use the convenience helper and hand it to `BrowserConfig` or `CrawlerRunConfig`:

```python
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai_proxyhat import proxyhat_proxy_config

proxy = proxyhat_proxy_config(api_key="ph_your_api_key", country="us")

async with AsyncWebCrawler(config=BrowserConfig(proxy_config=proxy)) as crawler:
    result = await crawler.arun("https://example.com", config=CrawlerRunConfig())
```

## Credentials

Pass them explicitly or via environment variables — options win over env:

| Option | Env var | Notes |
|---|---|---|
| `api_key` | `PROXYHAT_API_KEY` | Auto-selects an active sub-user with remaining traffic |
| `sub_user` | `PROXYHAT_SUBUSER` | Pick a specific sub-user by uuid or name (with an API key) |
| `username` | `PROXYHAT_USERNAME` | Explicit gateway `proxy_username` (skips the API) |
| `password` | `PROXYHAT_PASSWORD` | Explicit gateway `proxy_password` |

## Targeting

```python
strategy = ProxyHatRotationStrategy.from_credentials(
    api_key="ph_your_api_key",
    protocol="http",       # or "socks5"
    country="us",          # ISO code or "any" (default)
    region="california",
    city="new_york",
    filter="high",         # AI IP-quality tier
    sticky_ttl="30m",      # sticky-session lifetime (default "30m")
)
```

The same knobs (`country`, `region`, `city`, `filter`, plus `sticky`) are accepted by `proxyhat_proxy_config(...)`.

## How it works

Crawl4AI picks a proxy per request from the `CrawlerRunConfig` you pass to `arun` / `arun_many`:

- **Rotating (default).** With no `proxy_session_id`, Crawl4AI calls `get_next_proxy()`. We return a ProxyHat gateway `ProxyConfig` with a stable targeting username and **no** sticky token, so the gateway hands out a **fresh residential IP** for each new browser context.
- **Sticky (pinned IP).** Set a `proxy_session_id` and Crawl4AI calls `get_proxy_for_session(session_id, ttl)`. The first call mints one ProxyHat sticky session (a `-sid-…-ttl-…` gateway username) and caches it, so **every request sharing that session id exits from the same IP** until the TTL lapses or you release the session. Crawl4AI's `proxy_session_ttl` (seconds) maps to ProxyHat's sticky TTL; without one, `sticky_ttl` applies.

```python
# Pin one residential IP for a logical user session:
run_config = CrawlerRunConfig(
    proxy_rotation_strategy=strategy,
    proxy_session_id="user-42",
    proxy_session_ttl=1800,   # 30 minutes
)
```

Targeting and stickiness are both expressed in the gateway *username* using ProxyHat's targeting grammar (built by the official [`proxyhat`](https://pypi.org/project/proxyhat/) SDK); the sub-user password and gateway host/port stay constant. A single ProxyHat gateway fronts the whole residential pool, so there is no external proxy list to round-robin over — `add_proxies()` is a no-op kept for interface compatibility.

## License

MIT © [ProxyHat](https://proxyhat.com)
