"""Optional-dependency shim for Crawl4AI's proxy types.

``crawl4ai`` is a heavy dependency (Playwright and friends), so this package
imports its ``ProxyConfig`` / ``ProxyRotationStrategy`` when present and falls
back to minimal, field-compatible stand-ins otherwise. This keeps
``import crawl4ai_proxyhat`` cheap and lets the pure-logic tests run without a
full Crawl4AI install. To actually crawl you still need ``crawl4ai`` installed
(``pip install "crawl4ai-proxyhat[crawl4ai]"``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

try:  # pragma: no cover - exercised by whether crawl4ai is installed
    from crawl4ai import ProxyConfig as ProxyConfig  # type: ignore
except Exception:
    ProxyConfig = None  # type: ignore[assignment]

try:  # pragma: no cover
    from crawl4ai import ProxyRotationStrategy as ProxyRotationStrategy  # type: ignore
except Exception:
    try:  # pragma: no cover
        from crawl4ai.proxy_strategy import ProxyRotationStrategy as ProxyRotationStrategy  # type: ignore
    except Exception:
        ProxyRotationStrategy = None  # type: ignore[assignment]

#: ``True`` when the real Crawl4AI classes were imported.
CRAWL4AI_AVAILABLE = ProxyConfig is not None and ProxyRotationStrategy is not None


if ProxyConfig is None:  # pragma: no cover - only when crawl4ai is absent

    class ProxyConfig:  # type: ignore[no-redef]
        """Field-compatible stand-in for :class:`crawl4ai.ProxyConfig`."""

        def __init__(
            self,
            server: str,
            username: str | None = None,
            password: str | None = None,
            ip: str | None = None,
        ) -> None:
            self.server = server
            self.username = username
            self.password = password
            self.ip = ip

        def to_dict(self) -> dict:
            return {
                "server": self.server,
                "username": self.username,
                "password": self.password,
                "ip": self.ip,
            }

        def __repr__(self) -> str:
            return f"ProxyConfig(server={self.server!r}, username={self.username!r})"


if ProxyRotationStrategy is None:  # pragma: no cover - only when crawl4ai is absent

    class ProxyRotationStrategy(ABC):  # type: ignore[no-redef]
        """Abstract base mirroring :class:`crawl4ai.ProxyRotationStrategy`."""

        @abstractmethod
        async def get_next_proxy(self) -> ProxyConfig | None: ...

        @abstractmethod
        def add_proxies(self, proxies) -> None: ...

        @abstractmethod
        async def get_proxy_for_session(self, session_id: str, ttl: int | None = None) -> ProxyConfig | None: ...

        @abstractmethod
        async def release_session(self, session_id: str) -> None: ...

        @abstractmethod
        def get_session_proxy(self, session_id: str) -> ProxyConfig | None: ...

        @abstractmethod
        def get_active_sessions(self) -> dict: ...


__all__ = ["CRAWL4AI_AVAILABLE", "ProxyConfig", "ProxyRotationStrategy"]
