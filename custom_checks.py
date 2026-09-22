"""Best-effort, unauthenticated account checks not covered by Holehe."""
import asyncio
import hashlib
from typing import Any

import httpx


def _result(name: str, domain: str, method: str, *, others: Any = None, url: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "domain": domain,
        "method": method,
        "exists": True,
        "emailrecovery": None,
        "phoneNumber": None,
        "others": others,
        "url": url or f"https://{domain}",
    }


async def _pinterest(client: httpx.AsyncClient, email: str):
    try:
        response = await client.post(
            "https://www.pinterest.com/_ngapi/v3/users/email_available/",
            json={"email": email},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        if response.json().get("email_available") is False:
            return _result("Pinterest", "pinterest.com", "email_available")
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return None


async def _adobe(client: httpx.AsyncClient, email: str):
    try:
        response = await client.post(
            "https://auth.services.adobe.com/signin/v2/users/accounts",
            json={"username": email},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        if response.status_code in (401, 403, 429):
            return None
        data = response.json()
        text = str(data).lower()
        if any(key in data for key in ("account", "accounts", "idp", "identityProvider")) and "not found" not in text:
            return _result("Adobe", "adobe.com", "signin_account_lookup")
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return None


async def _grammarly(client: httpx.AsyncClient, email: str):
    try:
        response = await client.post(
            "https://auth.grammarly.com/v3/api/user/or/account",
            json={"email": email},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        if response.status_code in (401, 403, 404, 429):
            return None
        data = response.json()
        text = str(data).lower()
        if any(key in data for key in ("user", "account", "exists")) and not any(x in text for x in ("not found", "does not exist", "no account")):
            return _result("Grammarly", "grammarly.com", "account_lookup")
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return None


async def _gravatar(client: httpx.AsyncClient, email: str):
    digest = hashlib.md5(email.strip().lower().encode("utf-8"), usedforsecurity=False).hexdigest()
    profile_url = f"https://en.gravatar.com/{digest}.json"
    try:
        response = await client.get(profile_url, headers={"User-Agent": "OSINT-Lookup/2.1", "Accept": "application/json"})
        if response.status_code != 200:
            return None
        payload = response.json()
        profiles = payload.get("entry") if isinstance(payload, dict) else None
        if not isinstance(profiles, list) or not profiles:
            return None
        profile = profiles[0]
        if not isinstance(profile, dict):
            return None
        username = profile.get("preferredUsername")
        display_name = profile.get("displayName")
        details = {
            key: profile.get(key)
            for key in ("preferredUsername", "displayName", "aboutMe", "profileUrl", "thumbnailUrl", "urls", "accounts")
            if profile.get(key) not in (None, "", [], {})
        }
        return _result(
            "Gravatar",
            "gravatar.com",
            "md5_email_profile",
            others=details,
            url=profile.get("profileUrl") or (f"https://gravatar.com/{username}" if username else profile_url),
        )
    except (httpx.HTTPError, ValueError, TypeError):
        return None


async def _duolingo(client: httpx.AsyncClient, email: str):
    try:
        response = await client.get(
            "https://www.duolingo.com/2017-06-30/users",
            params={"email": email},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        if response.status_code != 200:
            return None
        payload = response.json()
        users = payload.get("users") if isinstance(payload, dict) else payload
        if not isinstance(users, list) or not users or not isinstance(users[0], dict):
            return None
        user = users[0]
        username = user.get("username") or user.get("userName")
        if not username:
            return None
        details = {key: user.get(key) for key in ("username", "name", "bio", "picture", "id") if user.get(key) not in (None, "")}
        return _result("Duolingo", "duolingo.com", "public_email_lookup", others=details, url=f"https://www.duolingo.com/profile/{username}")
    except (httpx.HTTPError, ValueError, TypeError):
        return None


async def run_custom_checks(email: str) -> list[dict[str, Any]]:
    """Return only positive, structurally confirmed checks; blocked endpoints are ignored."""
    timeout = httpx.Timeout(7.0, connect=4.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        checks = await asyncio.gather(
            _pinterest(client, email),
            _adobe(client, email),
            _grammarly(client, email),
            _gravatar(client, email),
            _duolingo(client, email),
            return_exceptions=True,
        )
    return [item for item in checks if isinstance(item, dict) and item.get("exists") is True]
