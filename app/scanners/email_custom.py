"""Best-effort, unauthenticated account checks not covered by holehe.

Ported from the previous custom_checks.py. Emits `found` on structurally
confirmed positives and `not_found` when the endpoint responded cleanly with
a negative; blocked endpoints (401/403/429) and transport errors are silently
skipped, as before.
"""

import asyncio
from typing import Optional

import httpx

from ..models import Result

_JSON_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def _res(site, domain, method, status, url=None, details=None):
    return Result(
        source="custom", category="email", site=site, status=status,
        url=url or f"https://{domain}",
        details={"method": method, **(details or {})},
    )


async def _pinterest(client: httpx.AsyncClient, email: str) -> Optional[Result]:
    try:
        r = await client.post(
            "https://www.pinterest.com/_ngapi/v3/users/email_available/",
            json={"email": email}, headers=_JSON_HEADERS)
        available = r.json().get("email_available")
        if available is False:
            return _res("Pinterest", "pinterest.com", "email_available", "found")
        if available is True:
            return _res("Pinterest", "pinterest.com", "email_available", "not_found")
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return None


async def _adobe(client: httpx.AsyncClient, email: str) -> Optional[Result]:
    try:
        r = await client.post(
            "https://auth.services.adobe.com/signin/v2/users/accounts",
            json={"username": email}, headers=_JSON_HEADERS)
        if r.status_code in (401, 403, 429):
            return None
        data = r.json()
        text = str(data).lower()
        if any(k in data for k in ("account", "accounts", "idp", "identityProvider")) \
                and "not found" not in text:
            return _res("Adobe", "adobe.com", "signin_account_lookup", "found")
        return _res("Adobe", "adobe.com", "signin_account_lookup", "not_found")
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return None


async def _grammarly(client: httpx.AsyncClient, email: str) -> Optional[Result]:
    try:
        r = await client.post(
            "https://auth.grammarly.com/v3/api/user/or/account",
            json={"email": email}, headers=_JSON_HEADERS)
        if r.status_code in (401, 403, 429):
            return None
        data = r.json()
        text = str(data).lower()
        if any(k in data for k in ("user", "account", "exists")) and not any(
                x in text for x in ("not found", "does not exist", "no account")):
            return _res("Grammarly", "grammarly.com", "account_lookup", "found")
        return _res("Grammarly", "grammarly.com", "account_lookup", "not_found")
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return None


async def _duolingo(client: httpx.AsyncClient, email: str) -> Optional[Result]:
    try:
        r = await client.get(
            "https://www.duolingo.com/2017-06-30/users",
            params={"email": email}, headers=_JSON_HEADERS)
        if r.status_code != 200:
            return None
        payload = r.json()
        users = payload.get("users") if isinstance(payload, dict) else payload
        if not isinstance(users, list):
            return None
        if not users:
            return _res("Duolingo", "duolingo.com", "public_email_lookup",
                        "not_found")
        user = users[0]
        username = user.get("username") or user.get("userName")
        if not isinstance(user, dict) or not username:
            return None
        details = {k: user.get(k) for k in ("username", "name", "bio", "picture", "id")
                   if user.get(k) not in (None, "")}
        return _res("Duolingo", "duolingo.com", "public_email_lookup", "found",
                    url=f"https://www.duolingo.com/profile/{username}",
                    details=details)
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return None


async def scan(email: str):
    timeout = httpx.Timeout(7.0, connect=4.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        checks = await asyncio.gather(
            _pinterest(client, email),
            _adobe(client, email),
            _grammarly(client, email),
            _duolingo(client, email),
            return_exceptions=True,
        )
    for item in checks:
        if isinstance(item, Result):
            yield item
