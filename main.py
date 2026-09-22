import asyncio
import importlib
import inspect
import pkgutil
import re
from typing import Literal
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

app = FastAPI(title="OSINT Lookup", version="2.0.0")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
URL_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)


def clean_url(value):
    if not isinstance(value, str):
        return None
    match = URL_RE.search(value)
    return match.group(0).rstrip(".,") if match else None


def flatten_other(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items() if v not in (None, "")) or None
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(v) for v in value if v not in (None, "")) or None
    return str(value)


def normalize_holehe(item):
    """Normalize Holehe's structured module response for the frontend."""
    if not isinstance(item, dict):
        return None
    name = str(item.get("name") or item.get("domain") or "Unknown service")
    domain = str(item.get("domain") or "").strip()
    exists = bool(item.get("exists"))
    url = clean_url(item.get("url") or item.get("profile_url") or item.get("profileUrl"))
    others = item.get("others")
    if isinstance(others, dict):
        for key, value in others.items():
            candidate = clean_url(value)
            if candidate:
                url = url or candidate
                break
    if not url and domain:
        url = f"https://{domain}" if not domain.startswith("http") else domain
    detail_parts = []
    method = item.get("method")
    if method:
        detail_parts.append(str(method))
    other_text = flatten_other(others)
    if other_text:
        detail_parts.append(other_text)
    return {
        "platform": name,
        "status": "found" if exists else "not_found",
        "label": "Found" if exists else "Not Found",
        "url": url,
        "phone": item.get("phoneNumber"),
        "recovery_email": item.get("emailrecovery"),
        "detail": " · ".join(detail_parts) or (domain or "Holehe result"),
    }


async def run_holehe(email: str, timeout: int = 90):
    """Run Holehe modules as a Python library and retain their dictionaries."""
    try:
        import httpx
        import trio
        import holehe.modules
    except ImportError as exc:
        return {"status": "unavailable", "results": [], "message": f"Holehe library unavailable: {exc}"}

    async def collect():
        results = []
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            modules = sorted(pkgutil.iter_modules(holehe.modules.__path__), key=lambda x: x.name)
            for module_info in modules:
                if module_info.name.startswith("_"):
                    continue
                try:
                    module = importlib.import_module(f"holehe.modules.{module_info.name}")
                    callback = getattr(module, module_info.name, None)
                    if callback is None:
                        callbacks = [v for v in vars(module).values() if inspect.iscoroutinefunction(v) and v.__module__ == module.__name__]
                        callback = callbacks[0] if callbacks else None
                    if callback is None:
                        continue
                    value = await callback(email, client)
                    normalized = normalize_holehe(value)
                    if normalized:
                        results.append(normalized)
                except Exception:
                    continue
        return results

    try:
        results = await asyncio.wait_for(asyncio.to_thread(trio.run, collect), timeout=timeout)
        return {"status": "ok", "results": results}
    except asyncio.TimeoutError:
        return {"status": "timeout", "results": [], "message": "Lookup timed out."}
    except Exception as exc:
        return {"status": "error", "results": [], "message": f"Holehe lookup failed: {exc}"}


async def run_command(command: list[str], timeout: int = 90) -> dict:
    try:
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill(); await process.wait()
        return {"status": "timeout", "results": [], "message": "Lookup timed out."}
    except FileNotFoundError:
        return {"status": "unavailable", "results": [], "message": f"Lookup engine is not installed: {command[0]}"}
    output = stdout.decode("utf-8", errors="replace")
    errors = stderr.decode("utf-8", errors="replace").strip()
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return {"status": "ok" if process.returncode == 0 else "completed_with_warnings", "lines": lines, "returncode": process.returncode, "stderr": errors[-2000:] if errors else None}


@app.get("/api/search")
async def search(type: Literal["username", "email", "auto"] = Query("auto"), query: str = Query(..., min_length=1, max_length=320)):
    query = query.strip()
    detected = "email" if type == "auto" and "@" in query else ("username" if type == "auto" else type)
    if detected == "email":
        if not EMAIL_RE.fullmatch(query):
            raise HTTPException(status_code=400, detail="Enter a valid email address.")
        raw = await run_holehe(query)
        return {"query": query, "type": detected, "engine": "Holehe", **raw}
    if not USERNAME_RE.fullmatch(query):
        raise HTTPException(status_code=400, detail="Use a username with letters, numbers, dots, underscores, or hyphens.")
    raw = await run_command(["sherlock", query, "--print-found", "--no-color"])
    lines = raw.pop("lines", [])
    raw["results"] = [{"platform": "Sherlock output", "status": "found", "label": "Results", "url": clean_url(line), "phone": None, "recovery_email": None, "detail": line} for line in lines]
    return {"query": query, "type": detected, "engine": "Sherlock", **raw}


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(INDEX_HTML)


INDEX_HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OSINT Lookup</title><style>
:root{color-scheme:dark;--line:#263653;--text:#e7eefc;--muted:#91a2c0;--accent:#65e6bd;--red:#ff8d9a;--yellow:#ffd479}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#182849,#0a0f1c 48%);font:16px system-ui,sans-serif;color:var(--text);min-height:100vh}.wrap{max-width:900px;margin:auto;padding:56px 20px}.eyebrow{color:var(--accent);font-weight:700;letter-spacing:.12em;text-transform:uppercase;font-size:.78rem}h1{font-size:clamp(2.3rem,7vw,4.8rem);line-height:1;margin:12px 0 16px}p{color:var(--muted);line-height:1.6}.card{background:#111a2ddc;border:1px solid var(--line);border-radius:22px;padding:24px;margin-top:30px;box-shadow:0 20px 70px #0005}.modes{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.mode{background:transparent;color:var(--muted);border:1px solid var(--line);padding:10px 14px;border-radius:999px;cursor:pointer}.mode.active{color:#062016;background:var(--accent);border-color:var(--accent);font-weight:700}.row{display:flex;gap:10px}.row input{flex:1;min-width:0;background:#0b1324;color:var(--text);border:1px solid var(--line);border-radius:12px;padding:15px;font-size:1rem}.go{background:var(--accent);border:0;border-radius:12px;padding:0 22px;font-weight:800;cursor:pointer}.go:disabled{opacity:.55}.status{margin-top:22px;color:var(--muted)}.results{display:grid;gap:10px;margin-top:16px}.result{background:#0b1324;border:1px solid var(--line);border-radius:13px;padding:14px}.top{display:flex;align-items:center;justify-content:space-between;gap:12px}.name{font-weight:700}.detail{color:var(--muted);font-size:.82rem;margin-top:4px;word-break:break-word}.metadata{display:flex;gap:7px;flex-wrap:wrap;margin-top:9px}.meta{font-size:.76rem;padding:5px 8px;border-radius:7px;background:#172844;color:#b8c9e8}.badge{font-size:.75rem;font-weight:700;padding:5px 9px;border-radius:999px;white-space:nowrap}.found{border-color:#2b9d78}.found .badge{background:#164e3d;color:var(--accent)}.not_found .badge{background:#263044;color:var(--muted)}a{color:var(--accent);font-size:.85rem}.link{display:inline-block;margin-top:9px;text-decoration:none;border:1px solid #2b9d78;border-radius:8px;padding:6px 9px}.notice{color:var(--red)}footer{margin-top:26px;font-size:.85rem;color:var(--muted)}
</style></head><body><main class="wrap"><div class="eyebrow">Open-source reconnaissance utility</div><h1>OSINT Lookup</h1><p>Search public username profiles with Sherlock or check email registrations with Holehe. Use responsibly and respect applicable laws and terms of service.</p><section class="card"><div class="modes"><button class="mode active" data-type="auto">Auto-detect</button><button class="mode" data-type="username">Username · Sherlock</button><button class="mode" data-type="email">Email · Holehe</button></div><form id="form"><div class="row"><input id="query" required placeholder="username or email address" autocomplete="off"><button class="go" id="go">Search</button></div></form><div id="status" class="status">Ready when you are.</div><div id="result" class="results"></div></section><footer>Results come from third-party tools and may be incomplete or inaccurate.</footer></main><script>
let selected='auto';const esc=s=>String(s??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));document.querySelectorAll('.mode').forEach(b=>b.onclick=()=>{selected=b.dataset.type;document.querySelectorAll('.mode').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelector('#query').placeholder=selected==='email'?'email address':selected==='username'?'username':'username or email address'});document.querySelector('#form').onsubmit=async e=>{e.preventDefault();let q=document.querySelector('#query').value.trim(),s=document.querySelector('#status'),r=document.querySelector('#result'),g=document.querySelector('#go');if(!q)return;g.disabled=true;r.innerHTML='';s.textContent='Running lookup…';try{let x=await fetch(`/api/search?type=${encodeURIComponent(selected)}&query=${encodeURIComponent(q)}`),d=await x.json();if(!x.ok)throw Error(d.detail||d.message||'Lookup failed');s.textContent=`${d.engine} completed for ${d.query} (${d.status}).`;r.innerHTML=(d.results||[]).map(v=>`<article class="result ${esc(v.status)}"><div class="top"><div><div class="name">${v.status==='found'?'✓ ':v.status==='rate_limited'?'! ':'– '}${esc(v.platform)}</div><div class="detail">${esc(v.detail)}</div></div><span class="badge">${esc(v.label)}</span></div><div class="metadata">${v.phone?`<span class="meta">Linked Phone: ${esc(v.phone)}</span>`:''}${v.recovery_email?`<span class="meta">Recovery Email: ${esc(v.recovery_email)}</span>`:''}</div>${v.url?`<a class="link" href="${esc(v.url)}" target="_blank" rel="noopener">View Profile / Site ↗</a>`:''}</article>`).join('')||'<div class="detail">No results were returned.</div>';if(d.message)r.insertAdjacentHTML('beforeend',`<div class="detail">${esc(d.message)}</div>`)}catch(err){s.innerHTML=`<span class="notice">${esc(err.message)}</span>`}finally{g.disabled=false}};
</script></body></html>'''
