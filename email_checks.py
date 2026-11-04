"""Account-existence checks written for this app, using public unauthenticated endpoints.

Every check answers one question for one site: does an account exist for this email?
A check returns a Finding with status "found", "not_found" or "unknown" ("unknown" means
the site blocked us or changed its API, never "no account"). Checks that can also read
public profile data fill in url, username and dates.
"""
import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import quote

import httpx

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
CHECK_TIMEOUT = 15.0


@dataclass
class Finding:
    status: str
    detail: str = ""
    url: str | None = None
    username: str | None = None
    created: str | None = None
    last_seen: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


FOUND, NOT_FOUND, UNKNOWN = "found", "not_found", "unknown"


def _ts(value: Any) -> str | None:
    """Format a unix timestamp or ISO string as a readable UTC date."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            seconds = float(value)
            if seconds > 1e11:
                seconds /= 1000
            return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%d")
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except (ValueError, OSError, OverflowError):
        return None


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


# --- email checks -----------------------------------------------------------------

async def firefox(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.post(
        "https://api.accounts.firefox.com/v1/account/status",
        json={"email": email},
        headers={"Content-Type": "application/json", "User-Agent": "osint-lookup/3.0"},  # a browser UA gets 406
    )
    data = _json(r)
    if r.status_code != 200 or not isinstance(data, dict) or "exists" not in data:
        return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")
    return Finding(FOUND if data["exists"] else NOT_FOUND, "Mozilla account status endpoint")


async def spotify(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.get(
        "https://spclient.wg.spotify.com/signup/public/v1/account",
        params={"validate": 1, "email": email},
    )
    data = _json(r) or {}
    status = data.get("status")
    if status == 20:
        return Finding(FOUND, "Signup validation says the address is already in use")
    if status == 1:
        return Finding(NOT_FOUND, "Signup validation says the address is free")
    return Finding(UNKNOWN, f"Signup validation returned status {status} ({r.status_code})")


async def microsoft(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.get(
        "https://odc.officeapps.live.com/odc/emailhrd/getidp",
        params={"hm": "1", "emailAddress": email},
    )
    body = r.text.strip().strip('"')
    if body in ("MSAccount", "OrgId", "Both"):
        label = {"MSAccount": "Personal Microsoft account", "OrgId": "Work or school account", "Both": "Personal and work account"}[body]
        return Finding(FOUND, label)
    if body == "Neither":
        return Finding(NOT_FOUND, "No Microsoft account for this address")
    return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")


async def adobe(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.post(
        "https://auth.services.adobe.com/signin/v2/users/accounts",
        json={"username": email},
        headers={"X-IMS-ClientId": "adobedotcom2", "Content-Type": "application/json"},
    )
    data = _json(r)
    if r.status_code != 200 or not isinstance(data, list):
        return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")
    if not data:
        return Finding(NOT_FOUND, "No Adobe ID for this address")
    kinds = sorted({str(item.get("type")) for item in data if isinstance(item, dict) and item.get("type")})
    return Finding(FOUND, "Adobe ID (" + ", ".join(kinds) + ")" if kinds else "Adobe ID")


async def atlassian(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.post("https://id.atlassian.com/rest/check-username", json={"username": email})
    action = (_json(r) or {}).get("action")
    if action == "signup":
        return Finding(NOT_FOUND, "Atlassian offers signup for this address")
    if action:
        return Finding(FOUND, f"Atlassian login exists (action: {action})")
    return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")


async def hubspot(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.post(
        "https://api.hubspot.com/login-api/v1/login",
        json={"email": email, "password": "not-a-real-password", "rememberLogin": False},
    )
    status = (_json(r) or {}).get("status")
    if status == "INVALID_USER":
        return Finding(NOT_FOUND, "HubSpot says the user does not exist")
    if status:
        return Finding(FOUND, f"HubSpot recognises the address ({status})")
    return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")


async def tumblr(client: httpx.AsyncClient, email: str) -> Finding:
    page = await client.get("https://www.tumblr.com/register")
    token = re.search(r'"API_TOKEN":"([^"]+)"', page.text)
    if not token:
        return Finding(UNKNOWN, "Could not read the signup page token")
    r = await client.post(
        "https://www.tumblr.com/api/v2/register/account/validate",
        json={"email": email, "tumblelog": "zq8k2u1x9qq", "password": "Xk29!dlsQwz"},
        headers={"Authorization": "Bearer " + token.group(1), "Origin": "https://www.tumblr.com"},
    )
    body = r.text.lower()
    if "user already exists" in body:
        return Finding(FOUND, "Signup validation says the user already exists")
    if r.status_code == 200:
        return Finding(NOT_FOUND, "Signup validation accepts the address")
    return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")


async def codecademy(client: httpx.AsyncClient, email: str) -> Finding:
    page = await client.get("https://www.codecademy.com/register")
    token = re.search(r'name="csrf-token" content="([^"]+)"', page.text)
    if not token:
        return Finding(UNKNOWN, "Could not read the signup page token")
    r = await client.post(
        "https://www.codecademy.com/register/validate",
        json={"user": {"email": email}},
        headers={"X-CSRF-Token": token.group(1), "Accept": "application/json", "Origin": "https://www.codecademy.com"},
    )
    if "already been taken" in r.text:
        return Finding(FOUND, "Signup validation says the address is taken")
    if r.status_code == 200:
        return Finding(NOT_FOUND, "Signup validation accepts the address")
    return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")


async def vivino(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.post(
        "https://www.vivino.com/api/login",
        json={"email": email, "password": "not-a-real-password"},
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    error = str((_json(r) or {}).get("error", "")).lower()
    if "does not exist" in error:
        return Finding(NOT_FOUND, "Login says the address does not exist")
    if error:
        return Finding(FOUND, "Login recognises the address")
    return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")


async def snapchat(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.post("https://bitmoji.api.snapchat.com/api/user/find", data={"email": email})
    if r.status_code == 200 and _json(r):
        kind = (_json(r) or {}).get("account_type")
        return Finding(FOUND, f"Snapchat/Bitmoji account ({kind})" if kind else "Snapchat/Bitmoji account")
    if r.status_code == 204:
        return Finding(NOT_FOUND, "No Snapchat/Bitmoji account for this address")
    return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")


async def wordpress(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.get(f"https://public-api.wordpress.com/rest/v1.1/users/{quote(email, safe='@')}/auth-options")
    data = _json(r)
    if not isinstance(data, dict):
        return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")
    if data.get("error") == "unknown_user":
        return Finding(NOT_FOUND, "WordPress.com does not know this address")
    if r.status_code == 200 or (r.status_code == 403 and data.get("error") == "email_login_not_allowed"):
        return Finding(FOUND, "WordPress.com recognises the address")
    return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")


async def zoho(client: httpx.AsyncClient, email: str) -> Finding:
    await client.get("https://accounts.zoho.com/signin")
    csrf = client.cookies.get("iamcsr") or ""
    r = await client.post(
        f"https://accounts.zoho.com/signin/v2/lookup/{email}",
        data={"mode": "primary", "cli_time": "1700000000000", "servicename": "ZohoHome", "serviceurl": "https://www.zoho.com/", "service_language": "en"},
        headers={"X-ZCSRF-TOKEN": f"iamcsrcoo={csrf}", "Origin": "https://accounts.zoho.com"},
    )
    data = _json(r) or {}
    if isinstance(data.get("lookup"), dict):
        return Finding(FOUND, "Zoho account lookup succeeded")
    if "does not exist" in r.text.lower():
        return Finding(NOT_FOUND, "Zoho says the user does not exist")
    return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")


async def komoot(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.post("https://www.komoot.com/v1/signin", json={"email": email, "reason": "header"})
    kind = (_json(r) or {}).get("type")
    if kind == "login":
        return Finding(FOUND, "Komoot asks this address to log in")
    if kind == "register":
        return Finding(NOT_FOUND, "Komoot offers signup for this address")
    return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")


async def chess_com(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.get("https://www.chess.com/callback/email/available", params={"email": email})
    data = _json(r) or {}
    if "isEmailAvailable" not in data:
        return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")
    return Finding(NOT_FOUND if data["isEmailAvailable"] else FOUND, "Signup email availability check")


async def twitter(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.get("https://api.twitter.com/i/users/email_available.json", params={"email": email})
    data = _json(r) or {}
    if "taken" not in data:
        return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")
    return Finding(FOUND if data["taken"] else NOT_FOUND, "Signup email availability check")


async def lastpass(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.get(
        "https://lastpass.com/create_account.php",
        params={"check": "avail", "skip": "1", "mistype": "1", "username": email},
    )
    body = r.text.strip().lower()
    if body == "no":
        return Finding(FOUND, "Signup says the address is already registered")
    if body == "ok":
        return Finding(NOT_FOUND, "Signup says the address is free")
    return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")


async def duolingo(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.get("https://www.duolingo.com/2017-06-30/users", params={"email": email})
    data = _json(r)
    if not isinstance(data, dict) or "users" not in data:
        return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")
    users = data["users"]
    if not users:
        return Finding(NOT_FOUND, "No Duolingo account for this address")
    user = users[0]
    username = user.get("username") or None
    profile = await _duolingo_profile(client, username) if username else {}
    extra = {k: user.get(k) for k in ("name", "streak") if user.get(k)}
    extra.update({k: profile.get(k) for k in ("totalXp", "streak") if profile.get(k)})
    return Finding(
        FOUND,
        "Public user lookup by email",
        url=f"https://www.duolingo.com/profile/{username}" if username else None,
        username=username,
        created=_ts(profile.get("creationDate")),
        extra=extra,
    )


async def _duolingo_profile(client: httpx.AsyncClient, username: str) -> dict[str, Any]:
    try:
        r = await client.get("https://www.duolingo.com/2017-06-30/users", params={"username": username})
        users = (_json(r) or {}).get("users") or []
        return users[0] if users and isinstance(users[0], dict) else {}
    except httpx.HTTPError:
        return {}


async def gravatar(client: httpx.AsyncClient, email: str) -> Finding:
    digest = hashlib.md5(email.strip().lower().encode("utf-8"), usedforsecurity=False).hexdigest()
    r = await client.get(f"https://en.gravatar.com/{digest}.json", headers={"Accept": "application/json"})
    if r.status_code == 404:
        return Finding(NOT_FOUND, "No Gravatar profile for this address")
    data = _json(r)
    entries = data.get("entry") if isinstance(data, dict) else None
    if r.status_code != 200 or not entries:
        return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")
    profile = entries[0]
    username = profile.get("preferredUsername")
    if str(username).startswith("g2-"):  # auto-generated placeholder, not a chosen name
        username = None
    accounts = [a.get("url") for a in profile.get("accounts", []) if isinstance(a, dict) and a.get("url")]
    extra = {k: profile.get(k) for k in ("displayName", "aboutMe", "currentLocation") if profile.get(k) and not str(profile.get(k)).startswith("g2-")}
    if accounts:
        extra["linked accounts"] = ", ".join(accounts[:6])
    return Finding(
        FOUND,
        "Public Gravatar profile",
        url=profile.get("profileUrl") or (f"https://gravatar.com/{username}" if username else None),
        username=username,
        extra=extra,
    )


async def github_commits(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.get(
        "https://api.github.com/search/commits",
        params={"q": f"author-email:{email}", "sort": "author-date", "order": "desc", "per_page": 30},
        headers={"Accept": "application/vnd.github+json"},
    )
    data = _json(r)
    if r.status_code != 200 or not isinstance(data, dict) or "total_count" not in data:
        return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")
    items = data.get("items") or []
    if not data["total_count"] or not items:
        return Finding(NOT_FOUND, "No public GitHub commits by this address")
    logins = [(i.get("author") or {}).get("login") for i in items]
    login = next((l for l in logins if l), None)
    repos = list(dict.fromkeys(i["repository"]["full_name"] for i in items if i.get("repository")))
    extra = {"public commits": data["total_count"], "repos": ", ".join(repos[:5])}
    last_seen = _ts(items[0]["commit"]["author"]["date"])
    if login:
        return Finding(FOUND, "Public GitHub commits by this address", url=f"https://github.com/{login}",
                       username=login, last_seen=last_seen, extra=extra)
    owner = repos[0].split("/")[0] if repos else None
    if owner:
        extra["note"] = f"address isn't linked to a GitHub login; commits are in repos owned by {owner}"
    return Finding(FOUND, "Public GitHub commits by this address",
                   url=f"https://github.com/{owner}" if owner else None, last_seen=last_seen, extra=extra)


async def internet_archive(client: httpx.AsyncClient, email: str) -> Finding:
    r = await client.post(
        "https://archive.org/services/xauthn/?op=login",
        data={"email": email, "password": "not-a-real-password-0"},
    )
    data = _json(r)
    reason = ((data or {}).get("values") or {}).get("reason") if isinstance(data, dict) else None
    if reason == "account_not_found":
        return Finding(NOT_FOUND, "No Internet Archive account")
    if reason == "account_bad_password":
        return Finding(FOUND, "Internet Archive account exists")
    return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")


EMAIL_CHECKS: list[tuple[str, str, Callable[[httpx.AsyncClient, str], Awaitable[Finding]]]] = [
    ("Adobe", "adobe.com", adobe),
    ("Atlassian", "atlassian.com", atlassian),
    ("Chess.com", "chess.com", chess_com),
    ("Codecademy", "codecademy.com", codecademy),
    ("Duolingo", "duolingo.com", duolingo),
    ("Firefox", "accounts.firefox.com", firefox),
    ("GitHub", "github.com", github_commits),
    ("Gravatar", "gravatar.com", gravatar),
    ("HubSpot", "hubspot.com", hubspot),
    ("Internet Archive", "archive.org", internet_archive),
    ("Komoot", "komoot.com", komoot),
    ("LastPass", "lastpass.com", lastpass),
    ("Microsoft", "microsoft.com", microsoft),
    ("Snapchat", "snapchat.com", snapchat),
    ("Spotify", "spotify.com", spotify),
    ("Tumblr", "tumblr.com", tumblr),
    ("Twitter / X", "x.com", twitter),
    ("Vivino", "vivino.com", vivino),
    ("WordPress.com", "wordpress.com", wordpress),
    ("Zoho", "zoho.com", zoho),
]


# --- username checks --------------------------------------------------------------

async def _github_user(client: httpx.AsyncClient, username: str) -> Finding:
    r = await client.get(f"https://api.github.com/users/{username}", headers={"Accept": "application/vnd.github+json"})
    if r.status_code == 404:
        return Finding(NOT_FOUND, "No GitHub user with this name")
    data = _json(r)
    if r.status_code != 200 or not isinstance(data, dict) or not data.get("login"):
        return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")
    extra = {k: data.get(k) for k in ("name", "company", "location", "public_repos", "followers") if data.get(k)}
    return Finding(
        FOUND, "Public GitHub profile", url=data.get("html_url"), username=data.get("login"),
        created=_ts(data.get("created_at")), last_seen=_ts(data.get("updated_at")), extra=extra,
    )


async def _chess_user(client: httpx.AsyncClient, username: str) -> Finding:
    r = await client.get(f"https://api.chess.com/pub/player/{username}")
    if r.status_code == 404:
        return Finding(NOT_FOUND, "No Chess.com member with this name")
    data = _json(r)
    if r.status_code != 200 or not isinstance(data, dict) or not data.get("username"):
        return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")
    extra = {k: data.get(k) for k in ("name", "followers", "status") if data.get(k)}
    if data.get("country"):
        extra["country"] = str(data["country"]).rstrip("/").rsplit("/", 1)[-1]
    return Finding(
        FOUND, "Public Chess.com profile", url=data.get("url"), username=data.get("username"),
        created=_ts(data.get("joined")), last_seen=_ts(data.get("last_online")), extra=extra,
    )


async def _duolingo_user(client: httpx.AsyncClient, username: str) -> Finding:
    r = await client.get("https://www.duolingo.com/2017-06-30/users", params={"username": username})
    data = _json(r)
    if r.status_code != 200 or not isinstance(data, dict) or not isinstance(data.get("users"), list):
        return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")
    if not data["users"] or not isinstance(data["users"][0], dict):
        return Finding(NOT_FOUND, "No Duolingo profile with this name")
    profile = data["users"][0]
    extra = {k: profile.get(k) for k in ("name", "streak", "totalXp") if profile.get(k)}
    return Finding(
        FOUND, "Public Duolingo profile", url=f"https://www.duolingo.com/profile/{username}",
        username=profile.get("username") or username, created=_ts(profile.get("creationDate")), extra=extra,
    )


async def _gravatar_user(client: httpx.AsyncClient, username: str) -> Finding:
    r = await client.get(f"https://en.gravatar.com/{username}.json", headers={"Accept": "application/json"})
    if r.status_code == 404:
        return Finding(NOT_FOUND, "No Gravatar profile with this name")
    entries = (_json(r) or {}).get("entry") if r.status_code == 200 else None
    if not entries:
        return Finding(UNKNOWN, f"Unexpected response ({r.status_code})")
    profile = entries[0]
    extra = {k: profile.get(k) for k in ("displayName", "aboutMe", "currentLocation") if profile.get(k)}
    return Finding(FOUND, "Public Gravatar profile", url=profile.get("profileUrl"), username=username, extra=extra)


USERNAME_CHECKS: list[tuple[str, str, Callable[[httpx.AsyncClient, str], Awaitable[Finding]]]] = [
    ("Chess.com", "chess.com", _chess_user),
    ("Duolingo", "duolingo.com", _duolingo_user),
    ("GitHub", "github.com", _github_user),
    ("Gravatar", "gravatar.com", _gravatar_user),
]


# --- runner -----------------------------------------------------------------------

def _card(name: str, domain: str, finding: Finding) -> dict[str, Any]:
    label = {FOUND: "Found", NOT_FOUND: "Not Found", UNKNOWN: "Couldn't check"}[finding.status]
    detail = finding.detail
    if finding.status == UNKNOWN:
        detail = f"{detail}. The site blocked the check or changed its API, so this is unknown, not a no.".lstrip(". ")
    meta = {}
    if finding.username:
        meta["Username"] = finding.username
    if finding.created:
        meta["Created"] = finding.created
    if finding.last_seen:
        meta["Last active"] = finding.last_seen
    for key, value in finding.extra.items():
        meta[str(key)] = str(value)
    return {
        "platform": name,
        "status": finding.status,
        "label": label,
        "url": finding.url or f"https://{domain}",
        "phone": None,
        "recovery_email": None,
        "detail": detail,
        "meta": meta,
    }


async def _run_one(client: httpx.AsyncClient, name: str, domain: str, func, value: str) -> dict[str, Any]:
    try:
        finding = await asyncio.wait_for(func(client, value), timeout=CHECK_TIMEOUT)
    except asyncio.TimeoutError:
        finding = Finding(UNKNOWN, "The check timed out")
    except Exception as exc:  # a broken check must not take the lookup down
        finding = Finding(UNKNOWN, f"The check failed: {type(exc).__name__}")
    return _card(name, domain, finding)


async def run_checks(checks: list, value: str) -> list[dict[str, Any]]:
    """Run every check concurrently, each with its own cookie jar."""
    async def one(name, domain, func):
        async with httpx.AsyncClient(timeout=CHECK_TIMEOUT, follow_redirects=True, headers=HEADERS) as client:
            return await _run_one(client, name, domain, func, value)

    return list(await asyncio.gather(*(one(*check) for check in checks)))


async def check_email(email: str) -> list[dict[str, Any]]:
    return await run_checks(EMAIL_CHECKS, email)


async def check_username(username: str) -> list[dict[str, Any]]:
    return await run_checks(USERNAME_CHECKS, username)
