import logging

from ..models import Result

TOP_SITES = 500

logger = logging.getLogger("osinthub.maigret")

_SITE_DICT = None


def _load_sites():
    global _SITE_DICT
    if _SITE_DICT is None:
        from maigret.db_updater import BUNDLED_DB_PATH
        from maigret.sites import MaigretDatabase
        db = MaigretDatabase().load_from_path(BUNDLED_DB_PATH)
        _SITE_DICT = db.ranked_sites_dict(top=TOP_SITES, disabled=False)
    return _SITE_DICT


async def scan(username: str):
    from maigret.checking import maigret
    from maigret.result import MaigretCheckStatus

    site_dict = _load_sites()
    results = await maigret(
        username,
        site_dict,
        logger=logger,
        timeout=10,
        id_type="username",
        is_parsing_enabled=True,
        max_connections=50,
        no_progressbar=True,
    )
    for site_name, data in (results or {}).items():
        check = data.get("status") if isinstance(data, dict) else getattr(data, "status", None)
        status = getattr(check, "status", None)
        url_user = data.get("url_user") if isinstance(data, dict) else getattr(data, "url_user", None)
        ids = getattr(check, "ids_data", None) if check else None
        if status == MaigretCheckStatus.CLAIMED:
            mapped = "found"
        elif status == MaigretCheckStatus.AVAILABLE:
            mapped = "not_found"
        else:
            mapped = "error"
        yield Result(
            source="maigret", category="username", site=site_name,
            status=mapped, url=url_user,
            details={"status": str(status), **({"ids": ids} if ids else {})},
        )
