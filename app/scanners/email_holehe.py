import asyncio

import httpx
from holehe.core import get_functions, import_submodules

from ..models import Result

SEMAPHORE = asyncio.Semaphore(20)
MODULE_TIMEOUT = 15


async def _run_module(fn, email, client):
    out = []
    async with SEMAPHORE:
        try:
            await asyncio.wait_for(fn(email, client, out), timeout=MODULE_TIMEOUT)
        except asyncio.TimeoutError:
            return [Result(source="holehe", category="email",
                           site=getattr(fn, "__name__", "unknown"),
                           status="error",
                           details={"error": f"timeout after {MODULE_TIMEOUT}s"})]
        except Exception as exc:
            return [Result(source="holehe", category="email",
                           site=getattr(fn, "__name__", "unknown"),
                           status="error", details={"error": str(exc)})]
    results = []
    for item in out:
        if item.get("rateLimit"):
            status = "rate_limited"
        elif item.get("exists"):
            status = "found"
        else:
            status = "not_found"
        details = {
            "method": item.get("method"),
            "emailrecovery": item.get("emailrecovery"),
            "phoneNumber": item.get("phoneNumber"),
            "others": item.get("others"),
        }
        results.append(Result(
            source="holehe", category="email",
            site=item.get("name") or getattr(fn, "__name__", "unknown"),
            status=status,
            url=f"https://{item.get('domain', '')}" or None,
            details={k: v for k, v in details.items() if v},
        ))
    if not results:
        results.append(Result(source="holehe", category="email",
                              site=getattr(fn, "__name__", "unknown"),
                              status="not_found",
                              details={"message": "no result emitted"}))
    return results


async def scan(email: str):
    functions = get_functions(import_submodules("holehe.modules"))
    async with httpx.AsyncClient(timeout=10) as client:
        tasks = [_run_module(fn, email, client) for fn in functions]
        for coro in asyncio.as_completed(tasks):
            try:
                for res in await coro:
                    yield res
            except Exception as exc:
                yield Result(source="holehe", category="email",
                             site="unknown", status="error",
                             details={"error": str(exc)})
