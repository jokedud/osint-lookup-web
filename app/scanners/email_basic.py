import hashlib
import re

import dns.resolver
import httpx

from ..models import Result

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "tempmail.com", "temp-mail.org",
    "10minutemail.com", "10minutemail.net", "yopmail.com", "trashmail.com",
    "trashmail.net", "getnada.com", "dispostable.com", "fakeinbox.com",
    "sharklasers.com", "guerrillamail.info", "grr.la", "guerrillamailblock.com",
    "pokemail.net", "spam4.me", "spamgourmet.com", "maildrop.cc",
    "harakirimail.com", "mailnesia.com", "mintemail.com", "mytemp.email",
    "mohmal.com", "tempail.com", "tempinbox.com", "throwawaymail.com",
    "emailondeck.com", "mailcatch.com", "inboxalias.com", "jetable.org",
    "wegwerfmail.de", "courrieltemporaire.com", "spambox.us", "getairmail.com",
    "filzmail.com", "mailexpire.com", "tempomail.fr", "burnermail.io",
}

PROVIDERS = {
    "gmail.com": "Google (Gmail)",
    "googlemail.com": "Google (Gmail)",
    "outlook.com": "Microsoft (Outlook)",
    "hotmail.com": "Microsoft (Hotmail)",
    "live.com": "Microsoft (Live)",
    "msn.com": "Microsoft (MSN)",
    "yahoo.com": "Yahoo",
    "yahoo.co.uk": "Yahoo",
    "ymail.com": "Yahoo",
    "proton.me": "Proton",
    "protonmail.com": "Proton",
    "pm.me": "Proton",
    "icloud.com": "Apple (iCloud)",
    "me.com": "Apple (iCloud)",
    "mac.com": "Apple (iCloud)",
    "aol.com": "AOL",
    "gmx.com": "GMX",
    "gmx.net": "GMX",
    "zoho.com": "Zoho",
}


def _res(site, status, url=None, details=None):
    return Result(
        source="basic", category="email", site=site,
        status=status, url=url, details=details or {},
    )


async def scan(email: str):
    """Async generator of basic email intelligence results."""
    email = email.strip().lower()

    if not EMAIL_RE.match(email):
        yield _res("Syntax", "error", details={"message": "Invalid email syntax"})
        return
    yield _res("Syntax", "info", details={"message": "Valid email syntax"})

    local, domain = email.rsplit("@", 1)

    if domain in PROVIDERS:
        yield _res("Provider", "info",
                   details={"provider": PROVIDERS[domain], "domain": domain})

    if domain in DISPOSABLE_DOMAINS:
        yield _res("Disposable", "found",
                   details={"message": "Domain is a known disposable/temp mail provider",
                            "domain": domain})
    else:
        yield _res("Disposable", "not_found",
                   details={"message": "Not a known disposable domain"})

    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=8)
        mx_hosts = sorted(
            [(r.preference, str(r.exchange).rstrip(".")) for r in answers]
        )
        yield _res("MX Records", "info", url=f"https://{domain}",
                   details={"mx": [f"{p} {h}" for p, h in mx_hosts]})
    except Exception as exc:
        yield _res("MX Records", "not_found",
                   details={"message": f"No MX records ({type(exc).__name__})"})

    md5 = hashlib.md5(email.encode()).hexdigest()
    gravatar_profile_url = f"https://gravatar.com/{md5}"
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            r = await client.get(
                f"https://www.gravatar.com/avatar/{md5}", params={"d": 404}
            )
            if r.status_code == 200:
                details = {"avatar": f"https://www.gravatar.com/avatar/{md5}"}
                try:
                    pj = await client.get(f"https://en.gravatar.com/{md5}.json")
                    if pj.status_code == 200:
                        entry = (pj.json().get("entry") or [{}])[0]
                        for k in ("displayName", "preferredUsername",
                                  "profileUrl", "aboutMe", "currentLocation"):
                            if entry.get(k):
                                details[k] = entry[k]
                except Exception:
                    pass
                yield _res("Gravatar", "found", url=gravatar_profile_url,
                           details=details)
            else:
                yield _res("Gravatar", "not_found",
                           details={"http_status": r.status_code})
    except Exception as exc:
        yield _res("Gravatar", "error", details={"error": str(exc)})
