"""Best-effort, unauthenticated account checks for services not covered by Holehe."""
import asyncio
from typing import Any
import httpx

def _result(name: str, domain: str, method: str, url: str | None = None) -> dict[str, Any]:
    return {"name": name, "domain": domain, "method": method, "exists": True, "emailrecovery": None, "phoneNumber": None, "others": None, "url": url or f"https://{domain}"}

async def _pinterest(client: httpx.AsyncClient, email: str):
    try:
        r = await client.post("https://www.pinterest.com/_ngapi/v3/users/email_available/", json={"email": email}, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        if r.json().get("email_available") is False: return _result("Pinterest", "pinterest.com", "email_available")
    except (httpx.HTTPError, ValueError, TypeError): pass
    return None

async def _adobe(client: httpx.AsyncClient, email: str):
    try:
        r = await client.post("https://auth.services.adobe.com/signin/v2/users/accounts", json={"username": email}, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        if r.status_code in (401, 403, 429): return None
        data = r.json(); text = str(data).lower()
        if any(k in data for k in ("account", "accounts", "idp", "identityProvider")) and "not found" not in text: return _result("Adobe", "adobe.com", "signin_account_lookup")
    except (httpx.HTTPError, ValueError, TypeError): pass
    return None

async def _grammarly(client: httpx.AsyncClient, email: str):
    try:
        r = await client.post("https://auth.grammarly.com/v3/api/user/or/account", json={"email": email}, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        if r.status_code in (401, 403, 404, 429): return None
        data = r.json(); text = str(data).lower()
        if any(k in data for k in ("user", "account", "exists")) and not any(x in text for x in ("not found", "does not exist", "no account")): return _result("Grammarly", "grammarly.com", "account_lookup")
    except (httpx.HTTPError, ValueError, TypeError): pass
    return None

async def run_custom_checks(email: str) -> list[dict[str, Any]]:
    """Return only positive, structurally confirmed checks; blocked endpoints are ignored."""
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        checks = await asyncio.gather(_pinterest(client, email), _adobe(client, email), _grammarly(client, email), return_exceptions=True)
    return [item for item in checks if isinstance(item, dict) and item.get("exists") is True]
