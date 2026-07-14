"""crawl4ai-proxyhat — route Crawl4AI crawls through ProxyHat residential proxies."""

from crawl4ai_proxyhat._compat import CRAWL4AI_AVAILABLE
from crawl4ai_proxyhat._resolve import resolve_credentials
from crawl4ai_proxyhat.strategy import ProxyHatRotationStrategy, proxyhat_proxy_config

__all__ = [
    "CRAWL4AI_AVAILABLE",
    "ProxyHatRotationStrategy",
    "proxyhat_proxy_config",
    "resolve_credentials",
]
__version__ = "0.1.1"
