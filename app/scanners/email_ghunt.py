import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from ..models import Result

CREDS_PATH = Path.home() / ".malfrats" / "ghunt" / "creds.m"
GHUNT_TIMEOUT = 90


def _ghunt_configured() -> bool:
    try:
        if not CREDS_PATH.is_file():
            return False
        data = json.loads(CREDS_PATH.read_text(encoding="utf-8"))
        return bool(data.get("cookies") and data.get("osids"))
    except Exception:
        return CREDS_PATH.is_file()


def _emit_value(results, site, value):
    if value in (None, "", {}, []):
        return
    if isinstance(value, dict):
        details = value
        url = value.get("url") or value.get("profile_url")
    else:
        details = {"value": str(value)}
        url = value if isinstance(value, str) and value.startswith("http") else None
    results.append(Result(source="ghunt", category="email", site=site,
                          status="found", url=url, details=details))


async def scan(email: str):
    if not _ghunt_configured():
        yield Result(
            source="ghunt", category="email", site="GHunt",
            status="info",
            details={"message": "GHunt credentials not found. Run `ghunt login` "
                                "to configure Google authentication."})
        return

    tmpf = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp = Path(tmpf.name)
    tmpf.close()
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c",
            "import sys; from ghunt.ghunt import main; "
            "sys.argv=['ghunt']+sys.argv[1:]; main()",
            "email", email, "--json", str(tmp),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(),
                                               timeout=GHUNT_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            yield Result(source="ghunt", category="email", site="GHunt",
                         status="error",
                         details={"error": f"timeout after {GHUNT_TIMEOUT}s"})
            return
        if proc.returncode != 0:
            yield Result(source="ghunt", category="email", site="GHunt",
                         status="error",
                         details={"error": stderr.decode(errors="replace")[-500:]})
            return
        if not tmp.is_file():
            yield Result(source="ghunt", category="email", site="GHunt",
                         status="not_found",
                         details={"message": "ghunt produced no output"})
            return
        try:
            data = json.loads(tmp.read_text(encoding="utf-8"))
        except Exception as exc:
            yield Result(source="ghunt", category="email", site="GHunt",
                         status="error", details={"error": str(exc)})
            return

        results = []
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    gaia = value.get("gaiaId") or value.get("personId")
                    if gaia:
                        value.setdefault("gaiaId", gaia)
                        _emit_value(results, f"Google account ({key})", value)
                    else:
                        _emit_value(results, key, value)
                else:
                    _emit_value(results, key, value)
        if not results:
            results.append(Result(source="ghunt", category="email",
                                  site="GHunt", status="not_found",
                                  details={"message": "No Google account data"}))
        for r in results:
            yield r
    except Exception as exc:
        yield Result(source="ghunt", category="email", site="GHunt",
                     status="error", details={"error": str(exc)})
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
