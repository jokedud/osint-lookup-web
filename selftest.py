"""Self-test for the email checks and GHunt: each must say "found" for a known registered
address and "not_found" for a random unused one. Run `python selftest.py` (exit code 1
when a check is broken) or GET /api/selftest on the deployed app. GHunt counts as broken
when GHUNT_MASTER_TOKEN is missing or Google rejects it, so an expired token shows up.
"""
import asyncio
import json
import secrets
import sys
from typing import Any

import httpx

from email_checks import EMAIL_CHECKS, FOUND, HEADERS, NOT_FOUND, _run_one
from ghunt_check import PLATFORM as GHUNT_PLATFORM, run_ghunt

DEFAULT_REGISTERED = "john@gmail.com"
REGISTERED_OVERRIDES = {"Firefox": "test@gmail.com"}


async def _status(name: str, domain: str, func, email: str) -> tuple[str, str]:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=HEADERS) as client:
        card = await _run_one(client, name, domain, func, email)
    return card["status"], card["detail"]


async def _ghunt_status(email: str) -> tuple[str, str]:
    card = next(c for c in (await run_ghunt(email))["results"] if c["platform"] == GHUNT_PLATFORM)
    return card["status"], card["detail"]


async def run_selftest() -> dict[str, Any]:
    unused = f"zq{secrets.token_hex(6)}@gmail.com"

    async def one(name, domain, func):
        registered = REGISTERED_OVERRIDES.get(name, DEFAULT_REGISTERED)
        status = _ghunt_status if func is None else lambda email: _status(name, domain, func, email)
        (pos, pos_detail), (neg, neg_detail) = await asyncio.gather(status(registered), status(unused))
        ok = pos == FOUND and neg == NOT_FOUND
        problem = None
        if not ok:
            problem = "; ".join(
                f"{label} address gave {status} ({detail})"
                for label, status, want, detail in (("registered", pos, FOUND, pos_detail), ("unused", neg, NOT_FOUND, neg_detail))
                if status != want
            )
        return {"check": name, "ok": ok, "registered": pos, "unused": neg, "problem": problem}

    results = await asyncio.gather(*(one(*check) for check in [*EMAIL_CHECKS, ("GHunt", "google.com", None)]))
    broken = [r["check"] for r in results if not r["ok"]]
    return {"ok": not broken, "passed": len(results) - len(broken), "total": len(results), "broken": broken, "results": list(results)}


if __name__ == "__main__":
    report = asyncio.run(run_selftest())
    for row in report["results"]:
        print(f"{'PASS' if row['ok'] else 'FAIL'}  {row['check']}" + (f": {row['problem']}" if row["problem"] else ""))
    print(json.dumps({k: report[k] for k in ("ok", "passed", "total", "broken")}))
    sys.exit(0 if report["ok"] else 1)
