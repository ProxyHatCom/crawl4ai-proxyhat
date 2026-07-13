"""Resolve ProxyHat gateway credentials from options or the environment."""

from __future__ import annotations

import os

from proxyhat import ProxyHat


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    value = value.strip() if value else None
    return value or None


def resolve_credentials(
    *,
    api_key: str | None = None,
    username: str | None = None,
    password: str | None = None,
    sub_user: str | None = None,
    base_url: str | None = None,
) -> tuple[str, str]:
    """Resolve a sub-user's gateway ``(proxy_username, proxy_password)``.

    Precedence (options win over env):

    1. explicit ``username`` + ``password`` (or ``PROXYHAT_USERNAME`` /
       ``PROXYHAT_PASSWORD``) — used directly, no API call;
    2. otherwise an ``api_key`` (or ``PROXYHAT_API_KEY``) looks up your
       sub-users and picks an active one with remaining traffic, or the one
       named by ``sub_user`` (``PROXYHAT_SUBUSER``, matched by uuid or name).

    Raises ``ValueError`` when nothing usable is found.
    """
    username = username or _env("PROXYHAT_USERNAME")
    password = password or _env("PROXYHAT_PASSWORD")
    if username and password:
        return username, password

    api_key = api_key or _env("PROXYHAT_API_KEY")
    if not api_key:
        raise ValueError(
            "crawl4ai-proxyhat: no credentials. Pass api_key= (or PROXYHAT_API_KEY), "
            "or username=/password= (PROXYHAT_USERNAME / PROXYHAT_PASSWORD)."
        )

    client = ProxyHat(api_key=api_key, base_url=base_url) if base_url else ProxyHat(api_key=api_key)
    users = client.sub_users.list()
    want = sub_user or _env("PROXYHAT_SUBUSER")
    want = want.strip() if want else None

    usable = [u for u in users if not u.suspended_at and (u.traffic_limit == 0 or u.used_traffic < u.traffic_limit)]
    if want:
        chosen = next((u for u in users if u.uuid == want or u.name == want), None)
    else:
        chosen = usable[0] if usable else None

    if chosen is None or not chosen.proxy_username or not chosen.proxy_password:
        raise ValueError(
            f'crawl4ai-proxyhat: no sub-user matched "{want}" (or it has no proxy credentials).'
            if want
            else "crawl4ai-proxyhat: no usable sub-user found (all suspended or out of traffic). "
            "Create one, top up, or pass sub_user=."
        )
    return chosen.proxy_username, chosen.proxy_password


__all__ = ["resolve_credentials"]
