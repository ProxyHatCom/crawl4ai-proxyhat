import pytest

from crawl4ai_proxyhat import ProxyHatRotationStrategy, proxyhat_proxy_config
from crawl4ai_proxyhat.strategy import _ttl_token


def make_strategy(**kwargs):
    return ProxyHatRotationStrategy("ph-1", "secret", **kwargs)


class TestProxyConfigBuilding:
    def test_server_host_and_port_http(self):
        cfg = proxyhat_proxy_config(username="ph-1", password="secret", country="us")
        assert cfg.server == "http://gate.proxyhat.com:8080"
        assert cfg.password == "secret"
        assert cfg.username == "ph-1-country-us"

    def test_socks5_uses_1080(self):
        cfg = proxyhat_proxy_config(username="ph-1", password="secret", protocol="socks5")
        assert cfg.server == "socks5://gate.proxyhat.com:1080"

    def test_geo_targeting_tokens(self):
        cfg = proxyhat_proxy_config(
            username="ph-1", password="secret", country="us", region="california", city="new york", filter="high"
        )
        assert cfg.username == "ph-1-country-us-region-california-city-new_york-filter-high"

    def test_default_country_any(self):
        cfg = proxyhat_proxy_config(username="ph-1", password="secret")
        assert cfg.username == "ph-1-country-any"

    def test_sticky_true_adds_session_and_ttl(self):
        cfg = proxyhat_proxy_config(username="ph-1", password="secret", sticky=True)
        assert "-sid-" in cfg.username
        assert "-ttl-30m" in cfg.username

    def test_sticky_string_ttl(self):
        cfg = proxyhat_proxy_config(username="ph-1", password="secret", sticky="12h")
        assert "-ttl-12h" in cfg.username


class TestRotating:
    @pytest.mark.asyncio
    async def test_get_next_proxy_is_rotating(self):
        strategy = make_strategy(country="us")
        cfg = await strategy.get_next_proxy()
        assert cfg.server == "http://gate.proxyhat.com:8080"
        assert cfg.username == "ph-1-country-us"
        assert "-sid-" not in cfg.username  # rotating, not pinned

    @pytest.mark.asyncio
    async def test_rotating_reuses_stable_username(self):
        strategy = make_strategy(country="us")
        first = await strategy.get_next_proxy()
        second = await strategy.get_next_proxy()
        # Same targeting username -> the gateway rotates the exit IP per connection.
        assert first.username == second.username


class TestSticky:
    @pytest.mark.asyncio
    async def test_session_pins_same_ip(self):
        strategy = make_strategy(country="de")
        first = await strategy.get_proxy_for_session("s1")
        second = await strategy.get_proxy_for_session("s1")
        assert "-sid-" in first.username
        assert first.username == second.username  # same pinned session

    @pytest.mark.asyncio
    async def test_distinct_sessions_get_distinct_pins(self):
        strategy = make_strategy()
        a = await strategy.get_proxy_for_session("a")
        b = await strategy.get_proxy_for_session("b")
        assert a.username != b.username

    @pytest.mark.asyncio
    async def test_ttl_seconds_converted_to_token(self):
        strategy = make_strategy()
        cfg = await strategy.get_proxy_for_session("s", ttl=1800)
        assert "-ttl-30m" in cfg.username

    @pytest.mark.asyncio
    async def test_default_sticky_ttl_used_without_ttl(self):
        strategy = make_strategy(sticky_ttl="1h")
        cfg = await strategy.get_proxy_for_session("s")
        assert "-ttl-1h" in cfg.username

    @pytest.mark.asyncio
    async def test_release_session_drops_pin(self):
        strategy = make_strategy()
        first = await strategy.get_proxy_for_session("s")
        await strategy.release_session("s")
        assert strategy.get_session_proxy("s") is None
        second = await strategy.get_proxy_for_session("s")
        assert first.username != second.username  # fresh session after release

    @pytest.mark.asyncio
    async def test_active_sessions_and_lookup(self):
        strategy = make_strategy()
        await strategy.get_proxy_for_session("s1")
        await strategy.get_proxy_for_session("s2")
        active = strategy.get_active_sessions()
        assert set(active) == {"s1", "s2"}
        assert strategy.get_session_proxy("s1") is active["s1"]

    @pytest.mark.asyncio
    async def test_expired_session_reissued(self):
        strategy = make_strategy()
        first = await strategy.get_proxy_for_session("s", ttl=1)
        # Force expiry by rewinding the stored creation time.
        proxy, _created, ttl = strategy._sessions["s"]
        strategy._sessions["s"] = (proxy, 0.0, ttl)
        assert strategy.get_session_proxy("s") is None
        assert strategy.get_active_sessions() == {}
        second = await strategy.get_proxy_for_session("s", ttl=1)
        assert first.username != second.username


class TestTtlToken:
    def test_conversions(self):
        assert _ttl_token(None) is None
        assert _ttl_token(0) is None
        assert _ttl_token(3600) == "1h"
        assert _ttl_token(7200) == "2h"
        assert _ttl_token(1800) == "30m"
        assert _ttl_token(90) == "90s"


class TestCredentialResolution:
    @pytest.mark.asyncio
    async def test_from_credentials_uses_resolver(self, monkeypatch):
        from types import SimpleNamespace

        users = [
            SimpleNamespace(
                uuid="g",
                name=None,
                proxy_username="good",
                proxy_password="pw",
                traffic_limit=0,
                used_traffic=0,
                suspended_at=None,
            )
        ]
        client = SimpleNamespace(sub_users=SimpleNamespace(list=lambda: users))
        monkeypatch.setattr("crawl4ai_proxyhat._resolve.ProxyHat", lambda **kw: client)

        strategy = ProxyHatRotationStrategy.from_credentials(api_key="ph_key", country="us")
        cfg = await strategy.get_next_proxy()
        assert cfg.username == "good-country-us"
        assert cfg.password == "pw"
