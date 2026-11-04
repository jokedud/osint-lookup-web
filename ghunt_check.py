"""Google account lookup through GHunt, limited to public account info."""
import asyncio
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import ghunt.globals as gb

if not hasattr(gb, "config"):
    gb.init_globals()

from ghunt.apis.calendar import CalendarHttp
from ghunt.apis.peoplepa import PeoplePaHttp
from ghunt.errors import GHuntInvalidSession
from ghunt.helpers import auth, gmaps, playgames
from ghunt.helpers.knowledge import get_user_type_definition
from ghunt.helpers.utils import get_httpx_client
from ghunt.objects.base import GHuntCreds

CREDS_PATH = Path(os.getenv("GHUNT_CREDS_PATH") or Path(tempfile.gettempdir()) / "ghunt" / "creds.m")
RECHECK_SECONDS = 600
PLATFORM = "Google Account (GHunt)"

_lock = asyncio.Lock()
_creds: GHuntCreds | None = None
_checked_at = 0.0


class GHuntNotConfigured(Exception):
    pass


def is_configured() -> bool:
    return bool(os.getenv("GHUNT_MASTER_TOKEN") or os.getenv("GHUNT_CREDS") or CREDS_PATH.is_file())


async def _authenticated_creds(client) -> GHuntCreds:
    """Load stored GHunt creds, or build them from GHUNT_CREDS / GHUNT_MASTER_TOKEN, then refresh cookies if needed."""
    global _creds, _checked_at
    async with _lock:
        if _creds and time.monotonic() - _checked_at < RECHECK_SECONDS:
            return _creds
        CREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        creds = GHuntCreds(creds_path=str(CREDS_PATH))
        try:
            creds.load_creds(silent=True)
        except GHuntInvalidSession:
            if blob := os.getenv("GHUNT_CREDS", "").strip():
                CREDS_PATH.write_text(blob, encoding="utf-8")
                creds.load_creds(silent=True)
            elif master_token := os.getenv("GHUNT_MASTER_TOKEN", "").strip():
                creds.android.master_token = master_token
                creds.cookies, creds.osids = {"a": "a"}, {"a": "a"}
                await auth.gen_cookies_and_osids(client, creds)
                creds.save_creds(silent=True)
            else:
                raise GHuntNotConfigured("Set GHUNT_MASTER_TOKEN to enable the Google account lookup.")
        await auth.check_and_gen(client, creds)
        _creds, _checked_at = creds, time.monotonic()
        return creds


def _card(platform: str, status: str, label: str, detail: str, url: str | None = None) -> dict[str, Any]:
    return {"platform": platform, "status": status, "label": label, "url": url, "phone": None, "recovery_email": None, "detail": detail}


async def _maps_card(client, gaia_id: str):
    url = f"https://www.google.com/maps/contrib/{gaia_id}/reviews"
    err, stats = await gmaps.get_reviews(client, gaia_id)
    if err == "failed":
        return _card("Google Maps", "unknown", "Rate limited", "Google blocked the Maps stats request; open the link to check manually.", url)
    counts = ", ".join(f"{k}: {v}" for k, v in stats.items() if v) if stats else ""
    if not counts:
        return _card("Google Maps", "not_found", "No public activity", "No public reviews, ratings or photos.", url)
    return _card("Google Maps", "found", "Found", f"Public contributions · {counts}", url)


async def _calendar_card(creds: GHuntCreds, client, email: str):
    found, calendar = await CalendarHttp(creds).get_calendar(client, email)
    if not found:
        return None
    details = [f"Timezone: {calendar.time_zone}"] if calendar.time_zone else []
    if calendar.summary:
        details.insert(0, f"Summary: {calendar.summary}")
    return _card("Google Calendar", "found", "Public calendar", " · ".join(details) or "Public calendar", f"https://calendar.google.com/calendar/embed?src={email}")


async def _play_games_card(creds: GHuntCreds, client, email: str):
    results = await playgames.search_player(creds, client, email)
    if not results:
        return None
    player = results[0]
    return _card("Google Play Games", "found", "Found", f"Username: {player.name} · Player ID: {player.id}", player.avatar_url or None)


async def _lookup(email: str) -> list[dict[str, Any]]:
    client = get_httpx_client()
    try:
        creds = await _authenticated_creds(client)
        found, target = await PeoplePaHttp(creds).people_lookup(client, email, params_template="max_details")
        if not found or "PROFILE" not in target.sourceIds:
            return [_card(PLATFORM, "not_found", "Not Found", "No public Google account for this email.")]
        details = [f"Gaia ID: {target.personId}"]
        if updated := target.sourceIds["PROFILE"].lastUpdated:
            details.append(f"Last profile edit: {updated:%Y-%m-%d} UTC")
        photo = target.profilePhotos.get("PROFILE")
        if photo and not photo.isDefault:
            details.append(f"Custom profile photo: {photo.url}")
        if info := target.profileInfos.get("PROFILE"):
            details += [f"Account type: {t} ({get_user_type_definition(t)})" for t in info.userTypes]
        if reach := target.inAppReachability.get("PROFILE"):
            if reach.apps:
                details.append("Services: " + ", ".join(reach.apps))
        if target.extendedData.gplusData.isEntrepriseUser:
            details.append("Workspace (enterprise) account")
        cards = [_card(PLATFORM, "found", "Found", " · ".join(details), photo.url if photo and not photo.isDefault else None)]
        extras = await asyncio.gather(
            _maps_card(client, target.personId),
            _calendar_card(creds, client, email),
            _play_games_card(creds, client, email),
            return_exceptions=True,
        )
        return cards + [c for c in extras if isinstance(c, dict)]
    finally:
        await client.aclose()


async def run_ghunt(email: str, timeout: int = 60) -> dict[str, Any]:
    if not is_configured():
        return {"status": "unavailable", "results": [_card(PLATFORM, "unavailable", "Not configured", "GHunt is not set up: add the GHUNT_MASTER_TOKEN environment variable.")]}
    try:
        return {"status": "ok", "results": await asyncio.wait_for(_lookup(email), timeout=timeout)}
    except asyncio.TimeoutError:
        return {"status": "timeout", "results": [_card(PLATFORM, "unknown", "Timed out", "GHunt lookup timed out.")]}
    except (Exception, SystemExit) as exc:
        global _creds
        _creds = None
        return {"status": "error", "results": [_card(PLATFORM, "unknown", "Error", f"GHunt lookup failed: {type(exc).__name__}: {exc}")]}
