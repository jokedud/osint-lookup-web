import asyncio
import json
import re

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from .models import Result
from .scanners import (email_basic, email_custom, email_ghunt, email_hibp,
                       email_holehe, phone, username_maigret,
                       username_sherlock)

router = APIRouter(prefix="/api")

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _sse(scanners):
    async def gen():
        queue = asyncio.Queue()
        counter = {"total": 0}
        pump = asyncio.create_task(_counted_pump(scanners, queue, counter))
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {item.model_dump_json()}\n\n"
            yield f"event: done\ndata: {json.dumps(counter)}\n\n"
        finally:
            pump.cancel()
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


async def _counted_pump(scanners, queue, counter):
    async def worker(scan_agen):
        try:
            async for res in scan_agen:
                counter[res.status] = counter.get(res.status, 0) + 1
                counter["total"] += 1
                await queue.put(res)
        except Exception as exc:
            counter["error"] = counter.get("error", 0) + 1
            await queue.put(Result(
                source="scanner", category="email", site="internal",
                status="error", details={"error": str(exc)}))
    await asyncio.gather(*[asyncio.create_task(worker(s)) for s in scanners],
                         return_exceptions=True)
    await queue.put(None)


@router.get("/scan/email")
async def scan_email(email: str = Query(...)):
    email = email.strip().lower()
    if not email or not EMAIL_RE.match(email):
        return StreamingResponse(
            iter([b'data: {"detail": "invalid email"}\n\n']),
            status_code=400, media_type="text/event-stream")
    return _sse([
        email_basic.scan(email),
        email_holehe.scan(email),
        email_custom.scan(email),
        email_hibp.scan(email),
        email_ghunt.scan(email),
    ])


@router.get("/scan/username")
async def scan_username(username: str = Query(..., min_length=1, max_length=64)):
    username = username.strip()
    if not username or "@" in username:
        return StreamingResponse(
            iter([b'data: {"detail": "invalid username"}\n\n']),
            status_code=400, media_type="text/event-stream")
    return _sse([
        username_maigret.scan(username),
        username_sherlock.scan(username),
    ])


@router.get("/scan/phone")
async def scan_phone(number: str = Query(..., min_length=3, max_length=20)):
    number = number.strip()
    if not re.fullmatch(r"\+?[\d\s().-]+", number):
        return StreamingResponse(
            iter([b'data: {"detail": "invalid phone number"}\n\n']),
            status_code=400, media_type="text/event-stream")
    return _sse([phone.scan(number)])
