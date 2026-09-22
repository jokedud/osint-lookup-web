import asyncio
import re
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

app = FastAPI(title="OSINT Lookup", version="1.0.0")

# Deliberately lightweight validation: holehe performs the actual verification.
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


async def run_command(command: list[str], timeout: int = 90) -> dict:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return {"status": "timeout", "results": [], "message": "Lookup timed out."}
    except FileNotFoundError:
        return {"status": "unavailable", "results": [], "message": f"Engine not installed: {command[0]}"}

    output = stdout.decode("utf-8", errors="replace")
    errors = stderr.decode("utf-8", errors="replace").strip()
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return {
        "status": "ok" if process.returncode == 0 else "completed_with_warnings",
        "results": lines,
        "returncode": process.returncode,
        "stderr": errors[-2000:] if errors else None,
    }


@app.get("/api/search")
async def search(
    type: Literal["username", "email", "auto"] = Query("auto"),
    query: str = Query(..., min_length=1, max_length=320),
):
    query = query.strip()
    detected = type
    if type == "auto":
        detected = "email" if "@" in query else "username"

    if detected == "email":
        if not EMAIL_RE.fullmatch(query):
            raise HTTPException(status_code=400, detail="Enter a valid email address.")
        # Holehe accepts the email as a positional argument; it has no --json flag.
        # The normal CLI output is captured and returned as result lines.
        result = await run_command(["holehe", query])
        engine = "Holehe"
    else:
        if not USERNAME_RE.fullmatch(query):
            raise HTTPException(status_code=400, detail="Use a username with letters, numbers, dots, underscores, or hyphens.")
        result = await run_command(["sherlock", query, "--print-found", "--no-color"])
        engine = "Sherlock"

    return {"query": query, "type": detected, "engine": engine, **result}


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(INDEX_HTML)


INDEX_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>OSINT Lookup</title>
<style>
:root{color-scheme:dark;--bg:#0a0f1c;--panel:#111a2d;--line:#263653;--text:#e7eefc;--muted:#91a2c0;--accent:#65e6bd;--danger:#ff8d9a}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#182849 0,#0a0f1c 45%);font:16px system-ui,sans-serif;color:var(--text);min-height:100vh}.wrap{max-width:900px;margin:auto;padding:56px 20px}.eyebrow{color:var(--accent);font-weight:700;letter-spacing:.12em;text-transform:uppercase;font-size:.78rem}h1{font-size:clamp(2.3rem,7vw,4.8rem);line-height:1;margin:12px 0 16px}p{color:var(--muted);line-height:1.6}.card{background:rgba(17,26,45,.86);border:1px solid var(--line);border-radius:22px;padding:24px;margin-top:30px;box-shadow:0 20px 70px #0005}.modes{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}.mode{background:transparent;color:var(--muted);border:1px solid var(--line);padding:10px 14px;border-radius:999px;cursor:pointer}.mode.active{color:#062016;background:var(--accent);border-color:var(--accent);font-weight:700}.row{display:flex;gap:10px}.row input{flex:1;min-width:0;background:#0b1324;color:var(--text);border:1px solid var(--line);border-radius:12px;padding:15px;font-size:1rem}.go{background:var(--accent);border:0;border-radius:12px;padding:0 22px;font-weight:800;cursor:pointer}.go:disabled{opacity:.55;cursor:wait}.status{margin-top:22px;color:var(--muted);white-space:pre-wrap}.result{background:#0b1324;border:1px solid var(--line);border-radius:12px;padding:16px;margin-top:14px;overflow:auto;white-space:pre-wrap;font:13px ui-monospace,monospace}.notice{color:var(--danger)}footer{margin-top:26px;font-size:.85rem;color:var(--muted)}
</style></head><body><main class="wrap"><div class="eyebrow">Open-source reconnaissance utility</div><h1>OSINT Lookup</h1><p>Search public username profiles with Sherlock or check email registrations with Holehe. Use responsibly and respect applicable laws and terms of service.</p><section class="card"><div class="modes"><button class="mode active" data-type="auto">Auto-detect</button><button class="mode" data-type="username">Username · Sherlock</button><button class="mode" data-type="email">Email · Holehe</button></div><form id="form"><div class="row"><input id="query" required placeholder="username or email address" autocomplete="off"><button class="go" id="go">Search</button></div></form><div id="status" class="status">Ready when you are.</div><div id="result"></div></section><footer>Results come from third-party tools and may be incomplete or inaccurate.</footer></main><script>
let selected='auto';document.querySelectorAll('.mode').forEach(b=>b.onclick=()=>{selected=b.dataset.type;document.querySelectorAll('.mode').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelector('#query').placeholder=selected==='email'?'email address':selected==='username'?'username':'username or email address'});document.querySelector('#form').onsubmit=async e=>{e.preventDefault();let q=document.querySelector('#query').value.trim(),s=document.querySelector('#status'),r=document.querySelector('#result'),g=document.querySelector('#go');if(!q)return;g.disabled=true;r.innerHTML='';s.textContent='Running lookup…';try{let x=await fetch(`/api/search?type=${encodeURIComponent(selected)}&query=${encodeURIComponent(q)}`),d=await x.json();if(!x.ok)throw Error(d.detail||'Lookup failed');s.textContent=`${d.engine} completed for ${d.query} (${d.status}).`;r.textContent=JSON.stringify(d.results,null,2)+(d.stderr?`\n\nWarnings:\n${d.stderr}`:'')}catch(err){s.innerHTML=`<span class="notice">${err.message}</span>`}finally{g.disabled=false}};
</script></body></html>'''