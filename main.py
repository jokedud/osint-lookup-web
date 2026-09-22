import asyncio
import re
from typing import Literal
import httpx
import trio
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from holehe.core import import_submodules, get_functions, launch_module
from custom_checks import run_custom_checks

app = FastAPI(title="OSINT Lookup", version="2.1.0")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
URL_RE = re.compile(r"https?://[^\s)]+", re.I)

def clean_url(value):
    if not isinstance(value, str): return None
    m = URL_RE.search(value)
    return m.group(0).rstrip(".,") if m else None

def flatten_other(value):
    if value is None: return None
    if isinstance(value, dict): return "; ".join(f"{k}: {v}" for k, v in value.items() if v not in (None, "")) or None
    if isinstance(value, (list, tuple, set)): return "; ".join(str(v) for v in value if v not in (None, "")) or None
    return str(value)

def normalize_holehe(item):
    if not isinstance(item, dict): return None
    name = str(item.get("name") or item.get("domain") or "Unknown service")
    domain = str(item.get("domain") or "").strip(); exists = bool(item.get("exists"))
    url = clean_url(item.get("url") or item.get("profile_url") or item.get("profileUrl"))
    others = item.get("others")
    if isinstance(others, dict):
        for value in others.values(): url = url or clean_url(value)
    url = url or (f"https://{domain}" if domain else None)
    details = [str(item["method"])] if item.get("method") else []
    if flatten_other(others): details.append(flatten_other(others))
    return {"platform": name, "status": "found" if exists else "not_found", "label": "Found" if exists else "Not Found", "url": url, "phone": item.get("phoneNumber"), "recovery_email": item.get("emailrecovery"), "detail": " · ".join(details) or domain or "Holehe result"}

async def run_holehe(email: str, timeout: int = 90):
    async def collect():
        modules = import_submodules("holehe.modules"); websites, out = get_functions(modules), []
        client = httpx.AsyncClient(timeout=20, follow_redirects=True)
        try:
            async with trio.open_nursery() as nursery:
                for website in websites: nursery.start_soon(launch_module, website, email, client, out)
        finally: await client.aclose()
        return sorted(out, key=lambda x: str(x.get("name", x.get("domain", ""))))
    try:
        raw = await asyncio.wait_for(asyncio.to_thread(trio.run, collect), timeout=timeout)
        combined = raw + await run_custom_checks(email); results, seen = [], set()
        for item in combined:
            result = normalize_holehe(item)
            if result and result["platform"] not in seen: seen.add(result["platform"]); results.append(result)
        return {"status": "ok", "results": results, "checked": len(raw), "custom_checked": 3}
    except asyncio.TimeoutError: return {"status": "timeout", "results": [], "message": "Lookup timed out."}
    except Exception as exc: return {"status": "error", "results": [], "message": f"Holehe lookup failed: {type(exc).__name__}: {exc}"}

async def run_command(command: list[str], timeout: int = 90):
    try:
        p = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE); stdout, stderr = await asyncio.wait_for(p.communicate(), timeout=timeout)
    except asyncio.TimeoutError: p.kill(); await p.wait(); return {"status": "timeout", "results": [], "message": "Lookup timed out."}
    except FileNotFoundError: return {"status": "unavailable", "results": [], "message": f"Lookup engine is not installed: {command[0]}"}
    lines = [x.strip() for x in stdout.decode(errors="replace").splitlines() if x.strip()]
    return {"status": "ok" if p.returncode == 0 else "completed_with_warnings", "lines": lines, "stderr": stderr.decode(errors="replace")[-2000:] or None}

@app.get("/api/search")
async def search(type: Literal["username", "email", "auto"] = Query("auto"), query: str = Query(..., min_length=1, max_length=320)):
    query = query.strip(); detected = "email" if type == "auto" and "@" in query else ("username" if type == "auto" else type)
    if detected == "email":
        if not EMAIL_RE.fullmatch(query): raise HTTPException(400, "Enter a valid email address.")
        return {"query": query, "type": detected, "engine": "Holehe + custom checks", **await run_holehe(query)}
    if not USERNAME_RE.fullmatch(query): raise HTTPException(400, "Use a username with letters, numbers, dots, underscores, or hyphens.")
    raw = await run_command(["sherlock", query, "--print-found", "--no-color"]); lines = raw.pop("lines", [])
    raw["results"] = [{"platform": "Sherlock output", "status": "found", "label": "Results", "url": clean_url(x), "phone": None, "recovery_email": None, "detail": x} for x in lines]
    return {"query": query, "type": detected, "engine": "Sherlock", **raw}

@app.get("/", response_class=HTMLResponse)
async def index(): return HTMLResponse(INDEX_HTML)

INDEX_HTML = '''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OSINT Lookup</title><style>body{margin:auto;max-width:900px;padding:40px 20px;background:#0a0f1c;color:#e7eefc;font:16px system-ui}input,button{padding:14px;border-radius:10px;border:1px solid #345;background:#111a2d;color:inherit}input{width:70%}button{background:#65e6bd;color:#062016;font-weight:bold}.result{margin:10px 0;padding:14px;border:1px solid #263653;border-radius:12px;background:#111a2d}.meta{display:inline-block;margin:8px 5px 0 0;padding:5px 8px;background:#172844;border-radius:7px;color:#b8c9e8}a{color:#65e6bd}</style></head><body><h1>OSINT Lookup</h1><p>Holehe plus best-effort custom checks for Pinterest, Adobe, and Grammarly.</p><form id="f"><input id="q" required placeholder="email or username"><button>Search</button></form><p id="s">Ready.</p><div id="r"></div><script>const e=x=>String(x??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));f.onsubmit=async x=>{x.preventDefault();s.textContent='Running lookup…';r.innerHTML='';try{let z=await fetch('/api/search?type=auto&query='+encodeURIComponent(q.value)),d=await z.json();if(!z.ok)throw Error(d.detail||d.message);s.textContent=d.engine+' completed ('+d.status+').';r.innerHTML=(d.results||[]).map(v=>'<article class="result"><b>'+e(v.platform)+'</b> — '+e(v.label)+'<div>'+e(v.detail)+'</div>'+(v.phone?'<span class="meta">Linked Phone: '+e(v.phone)+'</span>':'')+(v.recovery_email?'<span class="meta">Recovery Email: '+e(v.recovery_email)+'</span>':'')+(v.url?'<br><a target="_blank" rel="noopener" href="'+e(v.url)+'">View Profile / Site ↗</a>':'')+'</article>').join('')||'No results returned.'}catch(x){s.textContent=x.message}};</script></body></html>'''
