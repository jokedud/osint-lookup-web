import asyncio
import logging
import re
from typing import Literal
import time
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from email_checks import check_email, check_username
from ghunt_check import run_ghunt
from selftest import run_selftest

logger = logging.getLogger("osint_lookup")
app = FastAPI(title="OSINT Lookup", version="3.0.0")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
URL_RE = re.compile(r"https?://[^\s)]+", re.I)

def clean_url(value):
    if not isinstance(value, str): return None
    m = URL_RE.search(value)
    return m.group(0).rstrip(".,") if m else None

STATUS_ORDER = {"found": 0, "unknown": 1, "not_found": 2}

async def run_email_checks(email: str):
    try:
        results = sorted(await check_email(email), key=lambda r: (STATUS_ORDER.get(r["status"], 1), r["platform"]))
        return {"status": "ok", "results": results, "checked": len(results)}
    except Exception:
        logger.exception("Email checks failed")
        return {"status": "error", "results": [], "message": "Email checks failed."}

_selftest_cache = {"at": 0.0, "report": None}
SELFTEST_CACHE_SECONDS = 1800
_selftest_lock = asyncio.Lock()

async def run_command(command: list[str], timeout: int = 90):
    try:
        p = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE); stdout, stderr = await asyncio.wait_for(p.communicate(), timeout=timeout)
    except asyncio.TimeoutError: p.kill(); await p.wait(); return {"status": "timeout", "results": [], "message": "Lookup timed out."}
    except FileNotFoundError: return {"status": "unavailable", "results": [], "message": f"Lookup engine is not installed: {command[0]}"}
    lines = [x.strip() for x in stdout.decode(errors="replace").splitlines() if x.strip()]
    if stderr: logger.warning("%s stderr: %s", command[0], stderr.decode(errors="replace")[-2000:])
    return {"status": "ok" if p.returncode == 0 else "completed_with_warnings", "lines": lines}

@app.get("/api/search")
async def search(type: Literal["username", "email", "auto"] = Query("auto"), query: str = Query(..., min_length=1, max_length=320)):
    query = query.strip(); detected = "email" if type == "auto" and "@" in query else ("username" if type == "auto" else type)
    if detected == "email":
        if not EMAIL_RE.fullmatch(query): raise HTTPException(400, "Enter a valid email address.")
        checks, google = await asyncio.gather(run_email_checks(query), run_ghunt(query))
        checks["results"] = google["results"] + checks["results"]
        checks["counts"] = {k: sum(r["status"] == k for r in checks["results"]) for k in STATUS_ORDER}
        return {"query": query, "type": detected, "engine": "Own email checks + GHunt", **checks, "ghunt_status": google["status"]}
    if not USERNAME_RE.fullmatch(query): raise HTTPException(400, "Use a username with letters, numbers, dots, underscores, or hyphens.")
    profiles, raw = await asyncio.gather(check_username(query), run_command(["sherlock", "--print-found", "--no-color", "--", query])); lines = raw.pop("lines", [])
    profiles = sorted((p for p in profiles if p["status"] != "not_found"), key=lambda r: STATUS_ORDER.get(r["status"], 1))
    raw["results"] = profiles + [{"platform": "Sherlock output", "status": "found", "label": "Results", "url": clean_url(x), "phone": None, "recovery_email": None, "detail": x} for x in lines]
    return {"query": query, "type": detected, "engine": "Profile checks + Sherlock", **raw}

@app.get("/api/selftest")
async def selftest():
    """Run every email check against a registered and an unused address (cached for 30 minutes); 503 when a check is broken."""
    async with _selftest_lock:
        if _selftest_cache["report"] is None or time.time() - _selftest_cache["at"] > SELFTEST_CACHE_SECONDS:
            _selftest_cache["report"], _selftest_cache["at"] = await run_selftest(), time.time()
    report = _selftest_cache["report"]
    return JSONResponse(report, status_code=200 if report["ok"] else 503)

@app.get("/", response_class=HTMLResponse)
async def index(): return HTMLResponse(INDEX_HTML)

INDEX_HTML = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OSINT Lookup</title><style>body{margin:auto;max-width:900px;padding:40px 20px;background:#0a0f1c;color:#e7eefc;font:16px system-ui}input,button{padding:14px;border-radius:10px;border:1px solid #345;background:#111a2d;color:inherit}input{width:70%}button{background:#65e6bd;color:#062016;font-weight:bold}.result{margin:10px 0;padding:14px;border:1px solid #263653;border-radius:12px;background:#111a2d}.meta{display:inline-block;margin:8px 5px 0 0;padding:5px 8px;background:#172844;border-radius:7px;color:#b8c9e8}a{color:#65e6bd}</style></head><body><h1>OSINT Lookup</h1><p>Email: our own checks on 20 sites plus GHunt (public Google account info). Username: public profile checks (link, created, last active) plus Sherlock.</p><form id="f"><input id="q" required placeholder="email or username"><button>Search</button></form><p id="s">Ready.</p><div id="r"></div><script>const e=x=>String(x??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));f.onsubmit=async x=>{x.preventDefault();s.textContent='Running lookup…';r.innerHTML='';try{let z=await fetch('/api/search?type=auto&query='+encodeURIComponent(q.value)),d=await z.json();if(!z.ok)throw Error(d.detail||d.message);let n=d.counts;s.textContent=d.engine+' completed ('+d.status+').'+(n?' '+n.found+' found, '+n.unknown+" couldn't check, "+n.not_found+' not found.':'');r.innerHTML=(d.results||[]).map(v=>'<article class="result"><b>'+e(v.platform)+'</b> — '+e(v.label)+'<div>'+e(v.detail)+'</div>'+(v.phone?'<span class="meta">Linked Phone: '+e(v.phone)+'</span>':'')+(v.recovery_email?'<span class="meta">Recovery Email: '+e(v.recovery_email)+'</span>':'')+Object.entries(v.meta||{}).map(([k,m])=>'<span class="meta">'+e(k)+': '+e(m)+'</span>').join('')+(v.url?'<br><a target="_blank" rel="noopener" href="'+e(v.url)+'">View Profile / Site ↗</a>':'')+'</article>').join('')||'No results returned.'}catch(x){s.textContent=x.message}};</script></body></html>'''
