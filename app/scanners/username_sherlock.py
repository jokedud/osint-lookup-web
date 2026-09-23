import asyncio
from pathlib import Path

import sherlock_project

from ..models import Result

_SITE_DATA = None


def _load_sites():
    global _SITE_DATA
    if _SITE_DATA is None:
        from sherlock_project.sites import SitesInformation
        data_file = Path(sherlock_project.__file__).parent / "resources" / "data.json"
        sites = SitesInformation(data_file_path=str(data_file))
        _SITE_DATA = {s.name: s.information for s in sites}
    return _SITE_DATA


def _run(username):
    from sherlock_project.notify import QueryNotify
    from sherlock_project.result import QueryStatus
    from sherlock_project.sherlock import sherlock

    raw = sherlock(username, _load_sites(), QueryNotify(), timeout=10)
    out = []
    for site_name, data in (raw or {}).items():
        qres = data.get("status") if isinstance(data, dict) else None
        status = getattr(qres, "status", None)
        url = getattr(qres, "site_url_user", None) or data.get("url_user")
        if status == QueryStatus.CLAIMED:
            mapped = "found"
        elif status == QueryStatus.AVAILABLE:
            mapped = "not_found"
        else:
            mapped = "error"
        out.append(Result(
            source="sherlock", category="username", site=site_name,
            status=mapped, url=url,
            details={"status": str(status)},
        ))
    return out


async def scan(username: str):
    try:
        for res in await asyncio.to_thread(_run, username):
            yield res
    except Exception as exc:
        yield Result(source="sherlock", category="username", site="Sherlock",
                     status="error", details={"error": str(exc)})
