import os

import httpx

from ..models import Result

API_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/{email}"


async def scan(email: str):
    key = os.environ.get("HIBP_API_KEY")
    if not key:
        yield Result(source="hibp", category="email", site="HaveIBeenPwned",
                     status="info",
                     details={"message": "HIBP_API_KEY not configured"})
        return
    headers = {"hibp-api-key": key, "user-agent": "osint-hub"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(API_URL.format(email=email),
                                 params={"truncateResponse": "false"},
                                 headers=headers)
        if r.status_code == 404:
            yield Result(source="hibp", category="email",
                         site="HaveIBeenPwned", status="not_found",
                         url=f"https://haveibeenpwned.com/account/{email}",
                         details={"message": "No breaches found"})
            return
        r.raise_for_status()
        for breach in r.json():
            yield Result(
                source="hibp", category="email",
                site=f"HIBP: {breach.get('Name', 'unknown')}",
                status="found",
                url=f"https://haveibeenpwned.com/account/{email}",
                details={
                    "Name": breach.get("Name"),
                    "BreachDate": breach.get("BreachDate"),
                    "DataClasses": breach.get("DataClasses"),
                },
            )
    except Exception as exc:
        yield Result(source="hibp", category="email", site="HaveIBeenPwned",
                     status="error", details={"error": str(exc)})
