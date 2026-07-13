"""ProxyHat rotation strategy and helpers for Crawl4AI.

Crawl4AI resolves a proxy per request from a ``CrawlerRunConfig``:

* with no ``proxy_session_id`` it calls ``get_next_proxy()`` — we return a
  gateway config with **no** sticky token, so ProxyHat hands out a fresh
  residential IP on every new browser context;
* with a ``proxy_session_id`` it calls ``get_proxy_for_session(session_id, ttl)``
  — we mint one sticky ProxyHat session (a ``-sid-…-ttl-…`` username) the first
  time and cache it, so every request on that session exits from the same
  pinned IP until it is released or the TTL lapses.

A single ProxyHat gateway fronts the whole residential pool, so there is no
list of proxies to round-robin over; rotation and pinning are both expressed in
the gateway username's targeting grammar (built by the official ``proxyhat``
SDK).
"""

from __future__ import annotations

import asyncio
import time

from proxyhat import (
    PROXYHAT_GATEWAY,
    PROXYHAT_PORT_HTTP,
    PROXYHAT_PORT_SOCKS5,
    build_proxy_username,
)
from proxyhat.connection import ProxyProtocol

from crawl4ai_proxyhat._compat import ProxyConfig, ProxyRotationStrategy
from crawl4ai_proxyhat._resolve import resolve_credentials


def _ttl_token(ttl: int | None) -> str | None:
    """Turn Crawl4AI's integer-seconds session TTL into a ProxyHat duration.

    ``1800 -> "30m"``, ``3600 -> "1h"``, ``45 -> "45s"``. ``None`` means "let the
    caller's default apply".
    """
    if ttl is None:
        return None
    if ttl <= 0:
        return None
    if ttl % 3600 == 0:
        return f"{ttl // 3600}h"
    if ttl % 60 == 0:
        return f"{ttl // 60}m"
    return f"{ttl}s"


def _gateway_server(protocol: ProxyProtocol) -> str:
    port = PROXYHAT_PORT_SOCKS5 if protocol == "socks5" else PROXYHAT_PORT_HTTP
    return f"{protocol}://{PROXYHAT_GATEWAY}:{port}"


def _build_proxy_config(
    username: str,
    password: str,
    *,
    protocol: ProxyProtocol,
    targeting: dict,
    sticky: bool | str | None = None,
) -> ProxyConfig:
    """Build a Crawl4AI ``ProxyConfig`` pointed at the ProxyHat gateway.

    Targeting and stickiness live in the gateway *username*; the sub-user
    password and gateway host/port are constant.
    """
    user = build_proxy_username(
        username,
        country=targeting.get("country"),
        region=targeting.get("region"),
        city=targeting.get("city"),
        filter=targeting.get("filter"),
        sticky=sticky,
    )
    return ProxyConfig(server=_gateway_server(protocol), username=user, password=password)


def proxyhat_proxy_config(
    *,
    api_key: str | None = None,
    username: str | None = None,
    password: str | None = None,
    sub_user: str | None = None,
    base_url: str | None = None,
    protocol: ProxyProtocol = "http",
    country: str | None = None,
    region: str | None = None,
    city: str | None = None,
    filter: str | None = None,
    sticky: bool | str | None = None,
) -> ProxyConfig:
    """Return a single ProxyHat ``ProxyConfig`` for Crawl4AI.

    Resolves credentials (see :func:`resolve_credentials`) then builds one
    gateway config. Pass it straight to ``BrowserConfig(proxy_config=...)`` or
    ``CrawlerRunConfig(proxy_config=...)``. Rotating by default; set
    ``sticky=True`` (or a TTL string like ``"30m"``) to pin one residential IP.

    ```python
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    from crawl4ai_proxyhat import proxyhat_proxy_config

    proxy = proxyhat_proxy_config(api_key="ph_...", country="us")
    browser = BrowserConfig(proxy_config=proxy)
    async with AsyncWebCrawler(config=browser) as crawler:
        result = await crawler.arun("https://example.com", config=CrawlerRunConfig())
    ```
    """
    resolved_user, resolved_pass = resolve_credentials(
        api_key=api_key, username=username, password=password, sub_user=sub_user, base_url=base_url
    )
    targeting = {"country": country, "region": region, "city": city, "filter": filter}
    return _build_proxy_config(resolved_user, resolved_pass, protocol=protocol, targeting=targeting, sticky=sticky)


class ProxyHatRotationStrategy(ProxyRotationStrategy):
    """A Crawl4AI ``ProxyRotationStrategy`` backed by the ProxyHat gateway.

    Rotating by default: every ``get_next_proxy()`` yields a gateway config with
    no sticky token, so a fresh residential IP is used per browser context. When
    Crawl4AI runs with a ``proxy_session_id``, ``get_proxy_for_session()`` pins
    one ProxyHat sticky session (same exit IP) for that id.

    Construct with explicit gateway credentials, or use
    :meth:`from_credentials` to resolve them from an API key / environment.

    ```python
    from crawl4ai import CrawlerRunConfig
    from crawl4ai_proxyhat import ProxyHatRotationStrategy

    strategy = ProxyHatRotationStrategy.from_credentials(api_key="ph_...", country="us")
    run_config = CrawlerRunConfig(proxy_rotation_strategy=strategy)          # rotating
    sticky_config = CrawlerRunConfig(                                        # pinned IP
        proxy_rotation_strategy=strategy,
        proxy_session_id="user-42",
        proxy_session_ttl=1800,
    )
    ```
    """

    def __init__(
        self,
        username: str,
        password: str,
        *,
        protocol: ProxyProtocol = "http",
        country: str | None = None,
        region: str | None = None,
        city: str | None = None,
        filter: str | None = None,
        sticky_ttl: str = "30m",
    ) -> None:
        self._username = username
        self._password = password
        self._protocol: ProxyProtocol = protocol
        self._targeting = {"country": country, "region": region, "city": city, "filter": filter}
        self._sticky_ttl = sticky_ttl
        # session_id -> (proxy, created_at_epoch, ttl_seconds | None)
        self._sessions: dict[str, tuple[ProxyConfig, float, int | None]] = {}
        self._lock: asyncio.Lock | None = None

    @classmethod
    def from_credentials(
        cls,
        *,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        sub_user: str | None = None,
        base_url: str | None = None,
        protocol: ProxyProtocol = "http",
        country: str | None = None,
        region: str | None = None,
        city: str | None = None,
        filter: str | None = None,
        sticky_ttl: str = "30m",
    ) -> ProxyHatRotationStrategy:
        """Resolve credentials (API key or env) and build a strategy."""
        resolved_user, resolved_pass = resolve_credentials(
            api_key=api_key, username=username, password=password, sub_user=sub_user, base_url=base_url
        )
        return cls(
            resolved_user,
            resolved_pass,
            protocol=protocol,
            country=country,
            region=region,
            city=city,
            filter=filter,
            sticky_ttl=sticky_ttl,
        )

    def _session_lock(self) -> asyncio.Lock:
        # Created lazily so construction never needs a running event loop.
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    # --- ProxyRotationStrategy interface -------------------------------------

    async def get_next_proxy(self) -> ProxyConfig | None:
        """Rotating: a fresh residential IP for the next browser context."""
        return _build_proxy_config(self._username, self._password, protocol=self._protocol, targeting=self._targeting)

    def add_proxies(self, proxies) -> None:
        """No-op: a single ProxyHat gateway fronts the whole pool, so there is
        no external proxy list to extend. Present for interface compatibility."""

    async def get_proxy_for_session(self, session_id: str, ttl: int | None = None) -> ProxyConfig | None:
        """Sticky: pin one ProxyHat exit IP for ``session_id``.

        The first call mints a sticky session (``-sid-…-ttl-…`` username) and
        caches it; later calls reuse the same IP until the TTL lapses or the
        session is released.
        """
        async with self._session_lock():
            existing = self._sessions.get(session_id)
            if existing is not None:
                proxy, created_at, session_ttl = existing
                effective_ttl = ttl if ttl is not None else session_ttl
                if effective_ttl is None or (time.time() - created_at) < effective_ttl:
                    return proxy
                del self._sessions[session_id]

            token = _ttl_token(ttl) or self._sticky_ttl
            proxy = _build_proxy_config(
                self._username,
                self._password,
                protocol=self._protocol,
                targeting=self._targeting,
                sticky=token,
            )
            self._sessions[session_id] = (proxy, time.time(), ttl)
            return proxy

    async def release_session(self, session_id: str) -> None:
        """Drop a sticky session so its IP is no longer pinned."""
        async with self._session_lock():
            self._sessions.pop(session_id, None)

    def get_session_proxy(self, session_id: str) -> ProxyConfig | None:
        """Return the pinned proxy for an existing, unexpired session, else None."""
        existing = self._sessions.get(session_id)
        if existing is None:
            return None
        proxy, created_at, session_ttl = existing
        if session_ttl is not None and (time.time() - created_at) >= session_ttl:
            return None
        return proxy

    def get_active_sessions(self) -> dict[str, ProxyConfig]:
        """Map every unexpired sticky session id to its pinned proxy."""
        now = time.time()
        active: dict[str, ProxyConfig] = {}
        for session_id, (proxy, created_at, session_ttl) in self._sessions.items():
            if session_ttl is None or (now - created_at) < session_ttl:
                active[session_id] = proxy
        return active


__all__ = ["ProxyHatRotationStrategy", "proxyhat_proxy_config"]
