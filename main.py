import asyncio
import re
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

app = FastAPI(title="OSINT Lookup", version="1.0.0")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
HOLEHE_LINE = re.compile(r"^\[([+x-])\]\s*(.*)$", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)


def parse_holehe(lines: list[str]) -> list[dict]:
    """Convert Holehe's [+], [-], and [x] terminal lines into UI-safe data."""
    parsed = []
    statuses = {"+": ("found", "Found"), "-": ("not_found", "Not Found"), "x": ("rate_limited", "Rate Limited")}
    for line in lines:
        match = HOLEHE_LINE.match(line.strip())
        if not match:
            continue
        symbol, detail = match.groups()
        status, label = statuses[symbol.lower()]
        url_match = URL_RE.search(detail)
        url = url_match.group(0).rstrip(".,") if url_match else None
        service = detail.split(":", 1)[0].strip() if ":" in detail else detail
        parsed.append({"platform": service or "Unknown service", "status": status, "label": label, "url": url, "detail": detail})
    return parsed


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
        raw = await run_command(["holehe", query])
        result = parse_holehe(raw.pop("lines", []))
        engine = "Holehe"
    else:
        if not USERNAME_RE.fullmatch(query):
            raise HTTPException(status_code=400, detail="Use a username with letters, numbers, dots, underscores, or hyphens.")
        raw = await run_command(["sherlock", query, "--print-found", "--no-color"])
        result = [{"platform": "Sherlock output", "status": "found", "label": "Results", "url": None, "detail": line} for line in raw.pop("lines", [])]
        engine = "Sherlock"
    return {"query": query, "type": detected, "engine": engine, "results": result, **raw}


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(INDEX_HTML)


INDEX_HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OSINT Lookup</title><style>
:root{color-scheme:dark;--line:#263653;--text:#e7eefc;--muted:#91a2c0;--accent:#65e6bd;--red:#ff8d9a;--yellow:#ffd479}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#182849,#0a0f1c 48%);font:16px system-ui,sans-serif;color:var(--text);min-height:100vh}.wrap{max-width:900px;margin:auto;padding:56px 20px}.eyebrow{color:var(--accent);font-weight:700;letter-spacing:.12em;text-transform:uppercase;font-size:.78rem}h1{font-size:clamp(2.3rem,7vw,4.8rem);line-height:1;margin:12px 0 16px}p{color:var(--muted);line-height:1.6}.card{background:#111a2ddc;border:1px solid var(--line);border-radius:22px;padding:24px;margin-top:30px;box-shadow:0 20px 70px #0005}.modes{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.mode{background:transparent;color:var(--muted);border:1px solid var(--line);padding:10px 14px;border-radius:999px;cursor:pointer}.mode.active{color:#062016;background:var(--accent);border-color:var(--accent);font-weight:700}.row{display:flex;gap:10px}.row input{flex:1;min-width:0;background:#0b1324;color:var(--text);border:1px solid var(--line);border-radius:12px;padding:15px;font-size:1rem}.go{background:var(--accent);border:0;border-radius:12px;padding:0 22px;font-weight:800;cursor:pointer}.go:disabled{opacity:.55}.status{margin-top:22px;color:var(--muted)}.results{display:grid;gap:10px;margin-top:16px}.result{background:#0b1324;border:1px solid var(--line);border-radius:13px;padding:14px;display:flex;align-items:center;justify-content:space-between;gap:12px}.name{font-weight:700}.detail{color:var(--muted);font-size:.82rem;margin-top:4px;word-break:break-word}.badge{font-size:.75rem;font-weight:700;padding:5px 9px;border-radius:999px;white-space:nowrap}.found{border-color:#2b9d78}.found .badge{background:#164e3d;color:var(--accent)}.not_found .badge{background:#263044;color:var(--muted)}.rate_limited{border-color:#8b6730}.rate_limited .badge{background:#51401f;color:var(--yellow)}a{color:var(--accent);font-size:.85rem}.notice{color:var(--red)}footer{margin-top:26px;font-size:.85rem;color:var(--muted)}
</style></head><body><main class="wrap"><div class="eyebrow">Open-source reconnaissance utility</div><h1>OSINT Lookup</h1><p>Search public username profiles with Sherlock or check email registrations with Holehe. Use responsibly and respect applicable laws and terms of service.</p><section class="card"><div class="modes"><button class="mode active" data-type="auto">Auto-detect</button><button class="mode" data-type="username">Username · Sherlock</button><button class="mode" data-type="email">Email · Holehe</button></div><form id="form"><div class="row"><input id="query" required placeholder="username or email address" autocomplete="off"><button class="go" id="go">Search</button></div></form><div id="status" class="status">Ready when you are.</div><div id="result" class="results"></div></section><footer>Results come from third-party tools and may be incomplete or inaccurate.</footer></main><script>
let selected='auto';const esc=s=>String(s??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));document.querySelectorAll('.mode').forEach(b=>b.onclick=()=>{selected=b.dataset.type;document.querySelectorAll('.mode').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelector('#query').placeholder=selected==='email'?'email address':selected==='username'?'username':'username or email address'});document.querySelector('#form').onsubmit=async e=>{e.preventDefault();let q=document.querySelector('#query').value.trim(),s=document.querySelector('#status'),r=document.querySelector('#result'),g=document.querySelector('#go');if(!q)return;g.disabled=true;r.innerHTML='';s.textContent='Running lookup…';try{let x=await fetch(`/api/search?type=${encodeURIComponent(selected)}&query=${encodeURIComponent(q)}`),d=await x.json();if(!x.ok)throw Error(d.detail||'Lookup failed');s.textContent=`${d.engine} completed for ${d.query} (${d.status}).`;r.innerHTML=(d.results||[]).map(v=>`<article class="result ${esc(v.status)}"><div><div class="name">${v.status==='found'?'✓ ':v.status==='rate_limited'?'! ':'– '}${esc(v.platform)}</div><div class="detail">${esc(v.detail)}</div></div><div><span class="badge">${esc(v.label)}</span>${v.url?`<br><a href="${esc(v.url)}" target="_blank" rel="noopener">Open link ↗</a>`:''}</div></article>`).join('')||'<div class="detail">No parseable service results were returned.</div>';if(d.stderr)r.insertAdjacentHTML('beforeend',`<div class="detail">Warnings: ${esc(d.stderr)}</div>`)}catch(err){s.innerHTML=`<span class="notice">${esc(err.message)}</span>`}finally{g.disabled=false}};
</script></body></html>'''