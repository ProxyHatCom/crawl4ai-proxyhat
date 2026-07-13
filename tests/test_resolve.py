from types import SimpleNamespace

import pytest

from crawl4ai_proxyhat import resolve_credentials


def _sub_user(uuid, proxy_username, *, name=None, traffic_limit=0, used_traffic=0, suspended_at=None):
    return SimpleNamespace(
        uuid=uuid,
        name=name,
        proxy_username=proxy_username,
        proxy_password="pw-" + uuid,
        traffic_limit=traffic_limit,
        used_traffic=used_traffic,
        suspended_at=suspended_at,
    )


def _patch_sdk(monkeypatch, users):
    client = SimpleNamespace(sub_users=SimpleNamespace(list=lambda: users))
    monkeypatch.setattr("crawl4ai_proxyhat._resolve.ProxyHat", lambda **kw: client)


class TestExplicitCredentials:
    def test_username_password_win(self, monkeypatch):
        monkeypatch.delenv("PROXYHAT_API_KEY", raising=False)
        assert resolve_credentials(username="u", password="p") == ("u", "p")

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("PROXYHAT_USERNAME", "envu")
        monkeypatch.setenv("PROXYHAT_PASSWORD", "envp")
        assert resolve_credentials() == ("envu", "envp")

    def test_options_win_over_env(self, monkeypatch):
        monkeypatch.setenv("PROXYHAT_USERNAME", "envu")
        monkeypatch.setenv("PROXYHAT_PASSWORD", "envp")
        assert resolve_credentials(username="optu", password="optp") == ("optu", "optp")


class TestNoCredentials:
    def test_raises_without_anything(self, monkeypatch):
        for var in ("PROXYHAT_API_KEY", "PROXYHAT_USERNAME", "PROXYHAT_PASSWORD", "PROXYHAT_SUBUSER"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(ValueError, match="no credentials"):
            resolve_credentials()


class TestApiKeyResolution:
    def test_picks_active_sub_user(self, monkeypatch):
        for var in ("PROXYHAT_USERNAME", "PROXYHAT_PASSWORD", "PROXYHAT_SUBUSER"):
            monkeypatch.delenv(var, raising=False)
        users = [
            _sub_user("s", "susp", traffic_limit=100, used_traffic=1, suspended_at="2026-01-01"),
            _sub_user("g", "good", traffic_limit=0, used_traffic=9),
        ]
        _patch_sdk(monkeypatch, users)
        assert resolve_credentials(api_key="ph_key") == ("good", "pw-g")

    def test_skips_out_of_traffic(self, monkeypatch):
        for var in ("PROXYHAT_USERNAME", "PROXYHAT_PASSWORD", "PROXYHAT_SUBUSER"):
            monkeypatch.delenv(var, raising=False)
        users = [
            _sub_user("a", "maxed", traffic_limit=100, used_traffic=100),
            _sub_user("b", "ok", traffic_limit=100, used_traffic=5),
        ]
        _patch_sdk(monkeypatch, users)
        assert resolve_credentials(api_key="ph_key") == ("ok", "pw-b")

    def test_sub_user_by_name(self, monkeypatch):
        for var in ("PROXYHAT_USERNAME", "PROXYHAT_PASSWORD", "PROXYHAT_SUBUSER"):
            monkeypatch.delenv(var, raising=False)
        users = [
            _sub_user("a", "first", name="alpha"),
            _sub_user("b", "second", name="beta"),
        ]
        _patch_sdk(monkeypatch, users)
        assert resolve_credentials(api_key="ph_key", sub_user="beta") == ("second", "pw-b")

    def test_raises_when_no_usable(self, monkeypatch):
        for var in ("PROXYHAT_USERNAME", "PROXYHAT_PASSWORD", "PROXYHAT_SUBUSER"):
            monkeypatch.delenv(var, raising=False)
        users = [_sub_user("x", "x", traffic_limit=100, used_traffic=100)]
        _patch_sdk(monkeypatch, users)
        with pytest.raises(ValueError, match="no usable sub-user"):
            resolve_credentials(api_key="ph_key")

    def test_raises_when_named_sub_user_missing(self, monkeypatch):
        for var in ("PROXYHAT_USERNAME", "PROXYHAT_PASSWORD", "PROXYHAT_SUBUSER"):
            monkeypatch.delenv(var, raising=False)
        users = [_sub_user("a", "first", name="alpha")]
        _patch_sdk(monkeypatch, users)
        with pytest.raises(ValueError, match="no sub-user matched"):
            resolve_credentials(api_key="ph_key", sub_user="nope")
